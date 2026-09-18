import Markdown from '@/pages/ChatAgent/components/Markdown';

export default function EducationMarkdown({
  content,
  variant = 'lesson',
  className = '',
}: {
  content: string;
  variant?: 'lesson' | 'summary' | 'compact';
  className?: string;
}) {
  return (
    <div data-education-markdown={variant}>
      <Markdown variant="panel" content={content} className={className} />
    </div>
  );
}
