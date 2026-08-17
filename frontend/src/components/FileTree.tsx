'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight, File, Folder } from 'lucide-react';
import { api } from '@/lib/api';
import type { FileNode } from '@/lib/types';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

interface FileTreeProps {
  repoKey: string;
  selectedPath?: string | null;
  onSelectFile: (path: string) => void;
}

export function FileTree({ repoKey, selectedPath, onSelectFile }: FileTreeProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['file-tree', repoKey],
    queryFn: () => api.getFileTree(repoKey),
  });

  if (isLoading) {
    return (
      <div className="space-y-2 p-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-4 w-full" />
        ))}
      </div>
    );
  }

  return (
    <ScrollArea className="h-full">
      <div className="p-2">
        {data?.root.map((node) => (
          <TreeNode key={node.path} node={node} depth={0} selectedPath={selectedPath} onSelectFile={onSelectFile} />
        ))}
      </div>
    </ScrollArea>
  );
}

function TreeNode({
  node,
  depth,
  selectedPath,
  onSelectFile,
}: {
  node: FileNode;
  depth: number;
  selectedPath?: string | null;
  onSelectFile: (path: string) => void;
}) {
  const [open, setOpen] = useState(depth < 1);

  if (node.type === 'file') {
    return (
      <button
        type="button"
        onClick={() => onSelectFile(node.path)}
        className={cn(
          'flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-sm hover:bg-accent hover:text-accent-foreground',
          selectedPath === node.path && 'bg-accent text-accent-foreground',
        )}
        style={{ paddingLeft: depth * 14 + 8 }}
      >
        <File className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="truncate">{node.name}</span>
      </button>
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1 rounded-md px-2 py-1 text-left text-sm hover:bg-accent hover:text-accent-foreground"
        style={{ paddingLeft: depth * 14 + 8 }}
      >
        <ChevronRight className={cn('size-3.5 shrink-0 transition-transform', open && 'rotate-90')} />
        <Folder className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="truncate font-medium">{node.name}</span>
      </button>
      {open &&
        node.children.map((child) => (
          <TreeNode key={child.path} node={child} depth={depth + 1} selectedPath={selectedPath} onSelectFile={onSelectFile} />
        ))}
    </div>
  );
}
