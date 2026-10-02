import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BookNavigator } from '../components/BookNavigator';
import type { BookStructure } from '../types';

const structure: BookStructure = {
  textbook_id: 'book-1',
  structure_id: 'structure-1',
  schema_version: '2.1.0',
  warnings: [],
  structure: {
    schema_version: '2.1.0',
    book: { title: 'Reading Explorer 3' },
    source: { path: 'source.md', total_lines: 120 },
    coverage: { scope: 'all', excluded: [], omitted: [], gaps: [] },
    nodes: [
      {
        id: 'unit-1',
        title: 'Sports and Fitness',
        anchor: { start_line: 1, end_line: 80 },
        children: [
          {
            id: 'reading-a',
            title: "The World's Game",
            anchor: { start_line: 10, end_line: 40 },
            children: [],
          },
        ],
      },
      {
        id: 'appendix',
        title: 'Vocabulary Index',
        anchor: { start_line: 81, end_line: 120 },
        children: [],
      },
    ],
  },
  knowledge_points: [
    {
      knowledge_point_id: 'kp-db-1',
      skill_kp_id: 'sports-global-game',
      position: 1,
      title: '足球如何成为全球运动',
      unit_skill_node_id: 'unit-1',
      node_skill_ids: ['reading-a'],
      start_line: 10,
      end_line: 22,
      content_file: 'chapters/sports-global-game.md',
      material_available: true,
    },
    {
      knowledge_point_id: 'kp-db-2',
      skill_kp_id: 'sports-training',
      position: 2,
      title: '冠军的训练方法',
      unit_skill_node_id: 'unit-1',
      node_skill_ids: ['reading-a'],
      start_line: 23,
      end_line: 40,
      content_file: null,
      material_available: false,
    },
    {
      knowledge_point_id: 'kp-db-3',
      skill_kp_id: 'book-glossary',
      position: 3,
      title: '全书术语索引',
      unit_skill_node_id: null,
      node_skill_ids: ['appendix'],
      start_line: 81,
      end_line: 110,
      content_file: null,
      material_available: false,
    },
  ],
};

describe('BookNavigator', () => {
  it('groups knowledge points by unit and keeps ungrouped points explicit', () => {
    render(<BookNavigator structure={structure} />);

    expect(screen.getByRole('heading', { name: 'Sports and Fitness' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '未分组' })).toBeInTheDocument();
    expect(screen.getByText('足球如何成为全球运动')).toBeInTheDocument();
    expect(screen.getByLabelText('足球如何成为全球运动，已生成讲义')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '批量选择' })).not.toBeInTheDocument();
  });

  it('selects by skill KP id while retaining the database UUID in the structure', () => {
    const onSelectKnowledgePoint = vi.fn();
    render(
      <BookNavigator
        structure={structure}
        onSelectKnowledgePoint={onSelectKnowledgePoint}
      />,
    );

    fireEvent.click(screen.getByText('冠军的训练方法'));

    expect(onSelectKnowledgePoint).toHaveBeenCalledWith('sports-training');
  });

  it('filters knowledge points without turning search into URL state', () => {
    render(<BookNavigator structure={structure} />);

    fireEvent.change(screen.getByRole('searchbox', { name: '搜索教材内容' }), {
      target: { value: '冠军' },
    });

    expect(screen.getByText('冠军的训练方法')).toBeInTheDocument();
    expect(screen.queryByText('足球如何成为全球运动')).not.toBeInTheDocument();
    expect(screen.queryByText('全书术语索引')).not.toBeInTheDocument();
  });

  it('renders the recursive source tree and selects nodes independently from KPs', () => {
    const onSelectNode = vi.fn();
    render(<BookNavigator structure={structure} onSelectNode={onSelectNode} />);

    fireEvent.click(screen.getByRole('tab', { name: '原书目录' }));
    fireEvent.click(screen.getByRole('button', { name: "打开 The World's Game" }));

    expect(onSelectNode).toHaveBeenCalledWith('reading-a');
    expect(screen.getByRole('button', { name: '打开 Vocabulary Index' })).toBeInTheDocument();
  });

  it('enters batch mode explicitly and supports selecting a whole unit', () => {
    const onBatchModeChange = vi.fn();
    const onBatchSelectionChange = vi.fn();
    const { rerender } = render(
      <BookNavigator
        structure={structure}
        batchMode={false}
        onBatchModeChange={onBatchModeChange}
        selectedKnowledgePointIds={new Set()}
        onBatchSelectionChange={onBatchSelectionChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '批量选择' }));
    expect(onBatchModeChange).toHaveBeenCalledWith(true);

    rerender(
      <BookNavigator
        structure={structure}
        batchMode
        onBatchModeChange={onBatchModeChange}
        selectedKnowledgePointIds={new Set()}
        onBatchSelectionChange={onBatchSelectionChange}
      />,
    );
    const group = screen.getByTestId('kp-group-unit-1');
    fireEvent.click(within(group).getByRole('checkbox', { name: '选择 Sports and Fitness 全部知识点' }));

    expect(onBatchSelectionChange).toHaveBeenCalledWith(new Set(['kp-db-1', 'kp-db-2']));
  });
});
