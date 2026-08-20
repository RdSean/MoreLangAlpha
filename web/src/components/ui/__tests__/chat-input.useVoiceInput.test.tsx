import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useVoiceInput } from '../chat-input.useVoiceInput';

const toast = vi.fn();

vi.mock('../use-toast', () => ({
  useToast: () => ({ toast }),
}));

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn();

  constructor(readonly url: string) {
    MockWebSocket.instances.push(this);
  }

  open() { this.onopen?.(); }
  message(data: Record<string, unknown>) { this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent<string>); }
  fail() { this.onerror?.(); }
}

class MockRecognition {
  static instances: MockRecognition[] = [];
  continuous = false;
  interimResults = false;
  lang = '';
  onstart: (() => void) | null = null;
  onresult: ((event: SpeechRecognitionEvent) => void) | null = null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null = null;
  onend: (() => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
  abort = vi.fn();

  constructor() { MockRecognition.instances.push(this); }
}

const track = { stop: vi.fn() };
const processor = { connect: vi.fn(), disconnect: vi.fn(), onaudioprocess: null as ((event: AudioProcessingEvent) => void) | null };
const gain = { gain: { value: 1 }, connect: vi.fn(), disconnect: vi.fn() };
const audioContext = {
  sampleRate: 16_000,
  destination: {},
  createMediaStreamSource: vi.fn(() => ({ connect: vi.fn(), disconnect: vi.fn() })),
  createScriptProcessor: vi.fn(() => processor),
  createGain: vi.fn(() => gain),
  close: vi.fn().mockResolvedValue(undefined),
};

describe('useVoiceInput', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    MockRecognition.instances = [];
    vi.clearAllMocks();
    Object.defineProperty(window, 'WebSocket', { configurable: true, value: MockWebSocket });
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: MockRecognition });
    Object.defineProperty(window, 'AudioContext', { configurable: true, value: vi.fn(() => audioContext) });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('uses the backend stream before browser recognition and updates partial text', async () => {
    const setMessage = vi.fn();
    const { result } = renderHook(() => useVoiceInput({ message: '', setMessage, isLoading: false }));

    act(() => result.current.toggleListening());
    const socket = MockWebSocket.instances[0];
    expect(socket.url).toMatch(/\/ws\/v1\/speech\/transcribe$/);
    expect(MockRecognition.instances).toHaveLength(0);

    await act(async () => socket.open());
    act(() => socket.message({ type: 'partial', text: '你好' }));

    expect(setMessage).toHaveBeenLastCalledWith('你好');
  });

  it('falls back to browser recognition when backend startup fails', () => {
    const { result } = renderHook(() => useVoiceInput({ message: '', setMessage: vi.fn(), isLoading: false }));

    act(() => result.current.toggleListening());
    act(() => MockWebSocket.instances[0].fail());

    expect(MockRecognition.instances).toHaveLength(1);
    expect(MockRecognition.instances[0].start).toHaveBeenCalledOnce();
  });

  it('stops the socket and microphone tracks', async () => {
    const { result } = renderHook(() => useVoiceInput({ message: '', setMessage: vi.fn(), isLoading: false }));

    act(() => result.current.toggleListening());
    await act(async () => MockWebSocket.instances[0].open());
    act(() => result.current.stopListening());

    expect(MockWebSocket.instances[0].send).toHaveBeenCalledWith(JSON.stringify({ type: 'stop' }));
    expect(track.stop).toHaveBeenCalledOnce();
    expect(MockWebSocket.instances[0].close).not.toHaveBeenCalled();

    act(() => MockWebSocket.instances[0].message({ type: 'done' }));
    expect(MockWebSocket.instances[0].close).toHaveBeenCalledOnce();
  });

  it('ends quietly when the backend reports no speech', async () => {
    const { result } = renderHook(() => useVoiceInput({ message: '', setMessage: vi.fn(), isLoading: false }));

    act(() => result.current.toggleListening());
    await act(async () => MockWebSocket.instances[0].open());
    act(() => MockWebSocket.instances[0].message({ type: 'error', code: 'no_speech' }));

    expect(MockRecognition.instances).toHaveLength(0);
    expect(result.current.isListening).toBe(false);
  });

  it('stops recording after one minute', async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useVoiceInput({ message: '', setMessage: vi.fn(), isLoading: false }));

    act(() => result.current.toggleListening());
    await act(async () => MockWebSocket.instances[0].open());
    act(() => vi.advanceTimersByTime(60_000));

    expect(MockWebSocket.instances[0].send).toHaveBeenCalledWith(JSON.stringify({ type: 'stop' }));
    expect(track.stop).toHaveBeenCalledOnce();
    expect(result.current.isListening).toBe(false);
  });
});
