import type {
  StoryBlockRegistryItem,
  StoryLayoutRegistryItem,
  StoryReportBlock,
} from './types';

const orderedSlots = (
  block: StoryReportBlock,
  layout: StoryLayoutRegistryItem,
  category: string,
  usedSlots: Set<string>,
) => Object.entries(layout.slots)
  .filter(([slot, categories]) => !usedSlots.has(slot) && categories.includes(category))
  .map(([slot]) => slot)
  .sort((left, right) => Number(right === block.slot) - Number(left === block.slot));

/**
 * Reassigns blocks to unique compatible slots without changing their order or
 * configuration. Returning null means the layout cannot represent the page.
 */
export const assignBlocksToLayout = (
  blocks: StoryReportBlock[],
  layout: StoryLayoutRegistryItem,
  registryBlocks: StoryBlockRegistryItem[],
): StoryReportBlock[] | null => {
  if (blocks.length > layout.max_blocks) return null;

  const blockMetadata = new Map(registryBlocks.map((block) => [block.type, block]));
  const assigned: StoryReportBlock[] = [];
  const usedSlots = new Set<string>();

  const assignAt = (index: number): boolean => {
    if (index >= blocks.length) return true;
    const block = blocks[index];
    const metadata = blockMetadata.get(block.type);
    if (!metadata) return false;

    for (const slot of orderedSlots(block, layout, metadata.category, usedSlots)) {
      usedSlots.add(slot);
      assigned[index] = { ...block, slot };
      if (assignAt(index + 1)) return true;
      usedSlots.delete(slot);
    }
    return false;
  };

  return assignAt(0) ? assigned : null;
};

export const compatibleLayoutAssignments = (
  blocks: StoryReportBlock[],
  layouts: StoryLayoutRegistryItem[],
  registryBlocks: StoryBlockRegistryItem[],
) => layouts.flatMap((layout) => {
  const assignedBlocks = assignBlocksToLayout(blocks, layout, registryBlocks);
  return assignedBlocks ? [{ layout, blocks: assignedBlocks }] : [];
});

export const bestLayoutAssignment = (
  blocks: StoryReportBlock[],
  layouts: StoryLayoutRegistryItem[],
  registryBlocks: StoryBlockRegistryItem[],
  currentLayout?: string,
) => compatibleLayoutAssignments(blocks, layouts, registryBlocks)
  .sort((left, right) => {
    const leftCurrent = left.layout.key === currentLayout ? 0 : 1;
    const rightCurrent = right.layout.key === currentLayout ? 0 : 1;
    return leftCurrent - rightCurrent || left.layout.max_blocks - right.layout.max_blocks;
  })[0] || null;
