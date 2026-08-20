import { useCallback, useEffect, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { useTranslation } from 'react-i18next';
import { useToast } from './use-toast';
import { PcmPacketizer } from './voice-input.pcm';

const browserSpeechSupported = typeof window !== 'undefined'
  && !!(window.SpeechRecognition || window.webkitSpeechRecognition);
const backendSpeechSupported = typeof window !== 'undefined'
  && !!window.WebSocket
  && !!navigator.mediaDevices?.getUserMedia
  && !!window.AudioContext;

export const speechSupported = browserSpeechSupported || backendSpeechSupported;

function speechWebSocketUrl() {
  const base = import.meta.env.VITE_API_BASE_URL || window.location.origin;
  const url = new URL('/ws/v1/speech/transcribe', base);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

function canUseBackendSpeech() {
  return !!window.WebSocket
    && !!navigator.mediaDevices?.getUserMedia
    && !!window.AudioContext;
}

/** Voice input with a backend PCM stream and browser-recognition fallback. */
export function useVoiceInput({ message, setMessage, isLoading }: {
  message: string;
  setMessage: Dispatch<SetStateAction<string>>;
  isLoading?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const [isListening, setIsListening] = useState(false);
  const messageRef = useRef(message);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const packetizerRef = useRef<PcmPacketizer | null>(null);
  const socketOpenRef = useRef(false);
  const stoppingRef = useRef(false);
  const baseMessageRef = useRef('');
  const finalTranscriptRef = useRef('');
  const partialTranscriptRef = useRef('');

  useEffect(() => { messageRef.current = message; }, [message]);

  const publishTranscript = useCallback(() => {
    setMessage(baseMessageRef.current + finalTranscriptRef.current + partialTranscriptRef.current);
  }, [setMessage]);

  const stopBackend = useCallback((sendStop: boolean) => {
    const socket = socketRef.current;
    if (socket && sendStop && socketOpenRef.current) {
      const tail = packetizerRef.current?.flush();
      if (tail) socket.send(tail);
      socket.send(JSON.stringify({ type: 'stop' }));
    }
    socket?.close();
    socketRef.current = null;
    socketOpenRef.current = false;
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    processorRef.current = null;
    sourceRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    void contextRef.current?.close();
    contextRef.current = null;
    packetizerRef.current = null;
  }, []);

  const stopBrowser = useCallback(() => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
  }, []);

  const startBrowser = useCallback(() => {
    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionAPI) {
      toast({ title: t('chat.voice.serviceError'), variant: 'destructive' });
      setIsListening(false);
      return;
    }
    const recognition = new SpeechRecognitionAPI();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = i18n.language.startsWith('zh') ? 'zh-CN' : 'en-US';
    recognition.onstart = () => setIsListening(true);
    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = '';
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        if (event.results[index].isFinal) finalTranscriptRef.current += event.results[index][0].transcript;
        else interim += event.results[index][0].transcript;
      }
      partialTranscriptRef.current = interim;
      publishTranscript();
    };
    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error === 'not-allowed') toast({ title: t('chat.voice.permissionDenied'), variant: 'destructive' });
      else if (event.error !== 'aborted' && event.error !== 'no-speech') {
        toast({ title: t('chat.voice.serviceError'), variant: 'destructive' });
      }
      setIsListening(false);
      recognitionRef.current = null;
    };
    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
    };
    recognitionRef.current = recognition;
    recognition.start();
  }, [i18n.language, publishTranscript, t, toast]);

  const startBackend = useCallback(() => {
    if (!canUseBackendSpeech()) {
      startBrowser();
      return;
    }
    const socket = new WebSocket(speechWebSocketUrl());
    socketRef.current = socket;
    let receivedText = false;
    const fallback = () => {
      if (stoppingRef.current) return;
      stopBackend(false);
      if (!receivedText) startBrowser();
      else {
        toast({ title: t('chat.voice.serviceError'), variant: 'destructive' });
        setIsListening(false);
      }
    };

    socket.onopen = async () => {
      socketOpenRef.current = true;
      socket.send(JSON.stringify({ type: 'start' }));
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });
        if (socketRef.current !== socket) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        const context = new AudioContext();
        const source = context.createMediaStreamSource(stream);
        const processor = context.createScriptProcessor(4096, 1, 1);
        const packetizer = new PcmPacketizer(context.sampleRate);
        processor.onaudioprocess = (event) => {
          packetizer.push(event.inputBuffer.getChannelData(0)).forEach((packet) => socket.send(packet));
        };
        source.connect(processor);
        processor.connect(context.destination);
        streamRef.current = stream;
        contextRef.current = context;
        sourceRef.current = source;
        processorRef.current = processor;
        packetizerRef.current = packetizer;
        setIsListening(true);
      } catch {
        fallback();
      }
    };
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as { type?: string; text?: string };
        if (data.type === 'partial' && data.text != null) {
          receivedText = true;
          partialTranscriptRef.current = data.text;
          publishTranscript();
        } else if (data.type === 'final' && data.text != null) {
          receivedText = true;
          finalTranscriptRef.current += data.text;
          partialTranscriptRef.current = '';
          publishTranscript();
        } else if (data.type === 'error') {
          fallback();
        } else if (data.type === 'done') {
          stopBackend(false);
          setIsListening(false);
        }
      } catch {
        fallback();
      }
    };
    socket.onerror = fallback;
    socket.onclose = () => {
      if (socketRef.current === socket) fallback();
    };
  }, [publishTranscript, startBrowser, stopBackend, t, toast]);

  const stopListening = useCallback(() => {
    stoppingRef.current = true;
    stopBackend(true);
    stopBrowser();
    setIsListening(false);
    stoppingRef.current = false;
  }, [stopBackend, stopBrowser]);

  const toggleListening = useCallback(() => {
    if (isListening || socketRef.current || recognitionRef.current) {
      stopListening();
      return;
    }
    const current = messageRef.current.trim();
    baseMessageRef.current = current ? `${current} ` : '';
    finalTranscriptRef.current = '';
    partialTranscriptRef.current = '';
    startBackend();
  }, [isListening, startBackend, stopListening]);

  useEffect(() => {
    if (isLoading) stopListening();
  }, [isLoading, stopListening]);

  useEffect(() => () => stopListening(), [stopListening]);

  return { isListening, toggleListening, stopListening };
}
