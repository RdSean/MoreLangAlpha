/** A structured UI artifact attached to an agent message as prompt context. */
export interface WidgetContextSnapshot {
  widget_type: string;
  widget_id: string;
  label: string;
  description?: string;
  captured_at: string;
  text: string;
  data: Record<string, unknown>;
  image_jpeg_data_url?: string;
}
