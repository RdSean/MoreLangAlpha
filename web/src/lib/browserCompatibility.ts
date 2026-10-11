// Markdown dependencies require newer APIs during initialization and rendering.
import 'core-js/actual/array/at';
import 'core-js/actual/object/has-own';

type MediaListener = ((this: MediaQueryList, event: MediaQueryListEvent) => unknown) | EventListenerOrEventListenerObject;

// Both app hooks and Motion require the modern MediaQueryList API.
if (typeof window !== 'undefined' && typeof window.matchMedia === 'function'
  && typeof window.matchMedia('(min-width: 0px)').addEventListener !== 'function') {
  const matchMedia = window.matchMedia.bind(window);
  window.matchMedia = query => {
    const media = matchMedia(query);
    const listeners = new WeakMap<MediaListener, (event: MediaQueryListEvent) => void>();
    media.addEventListener = (type: string, listener: MediaListener | null, options?: boolean | AddEventListenerOptions) => {
      if (type !== 'change' || !listener || listeners.has(listener)) return;
      const wrapped = (event: MediaQueryListEvent) => {
        if (typeof options === 'object' && options.once) {
          media.removeListener(wrapped);
          listeners.delete(listener);
        }
        if (typeof listener === 'function') listener.call(media, event);
        else listener.handleEvent(event);
      };
      listeners.set(listener, wrapped);
      media.addListener(wrapped);
    };
    media.removeEventListener = (type: string, listener: MediaListener | null) => {
      if (type !== 'change' || !listener) return;
      const wrapped = listeners.get(listener);
      if (!wrapped) return;
      media.removeListener(wrapped);
      listeners.delete(listener);
    };
    return media;
  };
}
