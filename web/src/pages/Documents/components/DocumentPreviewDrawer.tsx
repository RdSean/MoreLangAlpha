import { useEffect, useRef, useState } from 'react';
import type {
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent as ReactMouseEvent,
} from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { FileText, Maximize2, Minimize2, X } from 'lucide-react';
import { motion } from 'framer-motion';
import { Badge } from '@/components/ui/badge';
import { useDocument } from '../hooks';
import type { DocumentContentTab } from './DocumentContentPane';
import DocumentContentPane from './DocumentContentPane';
import './DocumentPreviewDrawer.css';
import '../../ChatAgent/components/FilePanel.css';

/** The two halves of the file, in the order the strip shows them. */
const PREVIEW_TABS = [
  { id: 'source', labelKey: 'documents.preview.sourceTab' },
  { id: 'parsed', labelKey: 'documents.preview.parsedTab' },
] as const;

/** Same spring the other segmented controls in the app use (AnimatedTabs). */
const TAB_SPRING = { type: 'spring', bounce: 0.2, duration: 0.6 } as const;
const MIN_PANEL_WIDTH = 420;
const MAX_PANEL_WIDTH = 1100;
const DEFAULT_PANEL_WIDTH = 680;
const KEYBOARD_RESIZE_STEP = 20;

function clampPanelWidth(width: number): number {
  const maxWidth = Math.min(window.innerWidth - 24, MAX_PANEL_WIDTH);
  const minWidth = Math.min(MIN_PANEL_WIDTH, window.innerWidth - 24);
  return Math.max(minWidth, Math.min(maxWidth, Math.round(width)));
}

interface DocumentPreviewDrawerProps {
  open: boolean;
  documentId?: string;
  onOpenChange: (open: boolean) => void;
  onOpenParser?: (documentId: string) => void;
}

export default function DocumentPreviewDrawer({
  open,
  documentId,
  onOpenChange,
  onOpenParser,
}: DocumentPreviewDrawerProps) {
  const { t } = useTranslation();
  const documentRecord = useDocument(documentId);
  const [tab, setTab] = useState<DocumentContentTab>('source');
  const [panelWidth, setPanelWidth] = useState<number>();
  const [isDragging, setIsDragging] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const drawerRef = useRef<HTMLElement>(null);

  // Animate the sliding pill only when the tab actually changed: the drawer
  // also moves (a resize drag, a fullscreen toggle), and re-running the spring
  // for those would read as the pill sliding on its own.
  const prevTabRef = useRef(tab);
  const tabChanged = prevTabRef.current !== tab;
  useEffect(() => { prevTabRef.current = tab; }, [tab]);

  useEffect(() => {
    if (!open) return;
    setTab('source');
  }, [documentId, open]);

  useEffect(() => {
    if (!isDragging) return;
    const onMouseMove = (event: MouseEvent) => {
      setPanelWidth(clampPanelWidth(window.innerWidth - event.clientX));
    };
    const onMouseUp = () => setIsDragging(false);
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [isDragging]);

  useEffect(() => {
    const onFullscreenChange = () => setIsFullscreen(document.fullscreenElement === drawerRef.current);
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  const handleDividerMouseDown = (event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    const width = drawerRef.current?.getBoundingClientRect().width ?? panelWidth ?? 760;
    setPanelWidth(clampPanelWidth(width));
    setIsDragging(true);
  };

  const measurePanelWidth = () => {
    const renderedWidth = drawerRef.current?.getBoundingClientRect().width;
    if (!renderedWidth || !Number.isFinite(renderedWidth)) return undefined;
    const width = clampPanelWidth(renderedWidth);
    setPanelWidth(width);
    return width;
  };

  const handleDividerKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    let nextWidth: number | undefined;
    const currentWidth = panelWidth ?? measurePanelWidth() ?? DEFAULT_PANEL_WIDTH;
    if (event.key === 'ArrowLeft') {
      nextWidth = currentWidth - KEYBOARD_RESIZE_STEP;
    } else if (event.key === 'ArrowRight') {
      nextWidth = currentWidth + KEYBOARD_RESIZE_STEP;
    }
    if (nextWidth === undefined) return;

    event.preventDefault();
    setPanelWidth(clampPanelWidth(nextWidth));
  };

  const toggleFullscreen = async () => {
    if (document.fullscreenElement === drawerRef.current) {
      await document.exitFullscreen?.();
      return;
    }
    try {
      if (!drawerRef.current?.requestFullscreen) {
        setIsFullscreen(true);
        return;
      }
      await drawerRef.current.requestFullscreen();
    } catch {
      setIsFullscreen(true);
    }
  };

  const filename = documentRecord.data?.original_filename ?? t('documents.preview.titleFallback');

  return (
    <div
      className={`documents-preview-panel${open ? ' is-open' : ''}`}
      style={panelWidth ? { width: `${panelWidth}px`, flexBasis: `${panelWidth}px` } : undefined}
      aria-hidden={!open}
    >
      <aside
        ref={drawerRef}
        className={`documents-preview-drawer${isFullscreen ? ' is-fullscreen' : ''}`}
        aria-label={t('documents.preview.title')}
      >
        <div
          className={`chat-split-divider documents-preview-divider${isDragging ? ' dragging' : ''}`}
          onMouseDown={handleDividerMouseDown}
          onFocus={measurePanelWidth}
          onKeyDown={handleDividerKeyDown}
          role="separator"
          tabIndex={0}
          aria-orientation="vertical"
          aria-label={t('documents.preview.resize')}
          aria-valuemin={MIN_PANEL_WIDTH}
          aria-valuemax={MAX_PANEL_WIDTH}
          aria-valuenow={Math.round(panelWidth ?? DEFAULT_PANEL_WIDTH)}
        />
        <header className="documents-preview-header">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 shrink-0" aria-hidden="true" />
              <h2 className="truncate">{filename}</h2>
              {documentRecord.data?.parse_status && <Badge variant="muted">{t(`documents.status.${documentRecord.data.parse_status}`)}</Badge>}
            </div>
          </div>
          <div className="documents-preview-header-actions">
            {documentId && (
              <Link className="documents-preview-detail-link" to={`/documents/${encodeURIComponent(documentId)}`}>
                {t('documents.preview.viewDetail')}
              </Link>
            )}
            <button type="button" className="file-panel-icon-btn" onClick={() => void toggleFullscreen()} aria-label={isFullscreen ? t('documents.preview.exitFullscreen') : t('documents.preview.fullscreen')} title={isFullscreen ? t('documents.preview.exitFullscreen') : t('documents.preview.fullscreen')}>
              {isFullscreen ? <Minimize2 className="h-4 w-4" aria-hidden="true" /> : <Maximize2 className="h-4 w-4" aria-hidden="true" />}
            </button>
            <button type="button" className="file-panel-icon-btn" onClick={() => onOpenChange(false)} aria-label={t('documents.preview.close')}>
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </header>
        <div className="documents-preview-tabs documents-preview-segmented" role="tablist" aria-label={t('documents.preview.tabsLabel')}>
          {PREVIEW_TABS.map(({ id, labelKey }) => {
            const active = tab === id;
            return (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={active}
                className="documents-preview-tab"
                onClick={() => setTab(id)}
              >
                {/* One pill, carried between the two buttons by layoutId — the
                    same trick the app's other segmented controls use. */}
                {active && (
                  <motion.span
                    layoutId="documents-preview-tab"
                    className="documents-preview-tab-pill"
                    transition={tabChanged ? TAB_SPRING : { duration: 0 }}
                  />
                )}
                <span className="documents-preview-tab-label">{t(labelKey)}</span>
              </button>
            );
          })}
        </div>
        <div className="documents-preview-body">
          <div className="documents-preview-content file-panel-content">
            {open && documentId && (
              <DocumentContentPane
                documentId={documentId}
                document={documentRecord.data}
                activeTab={tab}
                isDragging={isDragging}
                onOpenParser={onOpenParser}
                onClose={() => onOpenChange(false)}
              />
            )}
          </div>
        </div>
      </aside>
    </div>
  );
}
