import { describe, expect, it } from 'vitest';
import { educationErrorMessage } from '../errorMessage';

describe('educationErrorMessage', () => {
  it('returns the FastAPI detail from an axios-style error', () => {
    expect(
      educationErrorMessage(
        {
          response: {
            data: {
              detail: '活动课程已使用其他生成要求，请先取消当前任务。',
            },
          },
        },
        '请稍后重试。',
      ),
    ).toBe('活动课程已使用其他生成要求，请先取消当前任务。');
  });

  it('falls back to the error message and then the caller fallback', () => {
    expect(educationErrorMessage(new Error('network failed'), 'fallback')).toBe(
      'network failed',
    );
    expect(educationErrorMessage({}, 'fallback')).toBe('fallback');
  });
});
