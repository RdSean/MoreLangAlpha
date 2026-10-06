import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
beforeEach(() => { void i18n.changeLanguage('zh-CN'); });
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
  it('keeps one indicator anchored in the tablist when switching all three views', () => {
    render(<BookNavigator structure={structure} onSelectOriginalNode={vi.fn()} />);
    const tablist = screen.getByRole('tablist');
    const indicator = tablist.querySelector('.book-navigator-indicator');
    expect(indicator?.parentElement).toBe(tablist);
    for (const name of ['原始教材', '文字目录', '知识点']) {
      fireEvent.click(screen.getByRole('tab', { name }));
      expect(tablist.querySelector('.book-navigator-indicator')).toBe(indicator);
      expect(tablist.querySelectorAll('.book-navigator-indicator')).toHaveLength(1);
      expect(screen.getByRole('tab', { name })).toHaveAttribute('aria-selected', 'true');
    }
  });

  it.each(['source', 'text'] as const)('keeps nested expansion independent from reading selection in %s', (view) => {
    const nested = structuredClone(structure);
    nested.structure.nodes[0].children![0].children = [{
      id: 'passage', title: 'Passage', anchor: { start_line: 12, end_line: 20 },
    }];
    const original = vi.fn();
    const text = vi.fn();
    render(<BookNavigator structure={nested} activeView={view} onSelectOriginalNode={original} onSelectNode={text} />);
    fireEvent.click(screen.getByRole('button', { name: "展开 The World's Game" }));
    expect(screen.getByRole('button', { name: '打开 Passage' })).toBeInTheDocument();
    expect(original).not.toHaveBeenCalled();
    expect(text).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '打开 Passage' }));
    expect(view === 'source' ? original : text).toHaveBeenCalledWith('passage');
    fireEvent.click(screen.getByRole('button', { name: "收起 The World's Game" }));
    expect(screen.queryByRole('button', { name: '打开 Passage' })).not.toBeInTheDocument();
  });

  it('collapses one knowledge chapter and toggles all chapters', () => {
    render(<BookNavigator structure={structure} />);
    fireEvent.click(screen.getByRole('button', { name: '收起 Sports and Fitness' }));
    expect(screen.queryByText('冠军的训练方法')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '展开 Sports and Fitness' }));
    expect(screen.getByText('冠军的训练方法')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '收起全部章节' }));
    expect(screen.queryByText('全书术语索引')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '展开全部章节' }));
    expect(screen.getByText('全书术语索引')).toBeInTheDocument();
  });
  it('separates original PDF and text directory selection and cycles three tabs', () => {
    const original = vi.fn();
    const text = vi.fn();
    render(<BookNavigator structure={structure} onSelectOriginalNode={original} onSelectNode={text} />);
    fireEvent.click(screen.getByRole('tab', { name: '原始教材' }));
    fireEvent.click(screen.getByRole('button', { name: "打开 The World's Game" }));
    expect(original).toHaveBeenCalledWith('reading-a');
    expect(text).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByRole('tab', { name: '原始教材' }), { key: 'ArrowRight' });
    const textTab = screen.getByRole('tab', { name: '文字目录' });
    expect(textTab).toHaveFocus();
    expect(textTab).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(screen.getByRole('button', { name: "打开 The World's Game" }));
    expect(text).toHaveBeenCalledWith('reading-a');
    fireEvent.keyDown(textTab, { key: 'ArrowRight' });
    expect(screen.getByRole('tab', { name: '知识点' })).toHaveFocus();
  });
  it('supports keyboard tab switching with an associated content panel', () => {
    render(<BookNavigator structure={structure} />);
    const knowledge = screen.getByRole('tab', { name: '知识点' });
    fireEvent.keyDown(knowledge, { key: 'ArrowRight' });
    const source = screen.getByRole('tab', { name: '原始教材' });
    expect(source).toHaveAttribute('aria-selected', 'true');
    expect(source).toHaveFocus();
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', source.id);
    fireEvent.keyDown(source, { key: 'Home' });
    expect(knowledge).toHaveAttribute('aria-selected', 'true');
  });
  it('groups knowledge points by unit and keeps ungrouped points explicit', () => {
    render(<BookNavigator structure={structure} />);

    expect(screen.getByRole('heading', { name: 'Sports and Fitness（2）' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '未分组（1）' })).toBeInTheDocument();
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

    fireEvent.click(screen.getByRole('tab', { name: '原始教材' }));
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
