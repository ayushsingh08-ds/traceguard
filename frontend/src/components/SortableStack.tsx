import React, { useState } from "react";
import { Reorder } from "motion/react";

export interface SortableItem {
  id: string;
}

interface SortableStackProps<T extends SortableItem> {
  items: T[];
  onReorder: (newItems: T[]) => void;
  renderItem: (item: T, isDragging: boolean) => React.ReactNode;
  keyExtractor?: (item: T) => string;
  className?: string;
  allowUndo?: boolean;
}

export function SortableStack<T extends SortableItem>({
  items,
  onReorder,
  renderItem,
  keyExtractor = (item) => item.id,
  className = "",
  allowUndo = true,
}: SortableStackProps<T>): React.ReactElement {
  const [history, setHistory] = useState<T[][]>([]);
  const [activeDragId, setActiveDragId] = useState<string | null>(null);

  const handleReorder = (newItems: T[]) => {
    if (allowUndo) {
      setHistory((prev) => [...prev.slice(-4), items]);
    }
    onReorder(newItems);
  };

  const handleUndo = () => {
    if (history.length === 0) return;
    const previous = history[history.length - 1];
    setHistory((prev) => prev.slice(0, -1));
    onReorder(previous);
  };

  return (
    <div className={`space-y-3 ${className}`}>
      {allowUndo && history.length > 0 && (
        <div className="flex justify-end">
          <button
            onClick={handleUndo}
            className="text-xs px-2.5 py-1 rounded-md border border-gray-300 dark:border-darkborder bg-white dark:bg-darkcard text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors shadow-sm flex items-center space-x-1"
          >
            <span>&larr;</span>
            <span>Undo Reorder</span>
          </button>
        </div>
      )}

      <Reorder.Group
        axis="y"
        values={items}
        onReorder={handleReorder}
        className="space-y-2.5"
      >
        {items.map((item) => {
          const itemId = keyExtractor(item);
          const isDragging = activeDragId === itemId;

          return (
            <Reorder.Item
              key={itemId}
              value={item}
              id={itemId}
              onDragStart={() => setActiveDragId(itemId)}
              onDragEnd={() => setActiveDragId(null)}
              className={`solid-card p-4 transition-shadow cursor-grab active:cursor-grabbing select-none relative ${
                isDragging
                  ? "shadow-lg border-brand-500 scale-[1.01] z-10 ring-2 ring-brand-500/20"
                  : "hover:border-gray-300 dark:hover:border-darkborder"
              }`}
              whileDrag={{ scale: 1.015 }}
            >
              <div className="flex items-start space-x-3">
                <div
                  className="mt-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 cursor-grab active:cursor-grabbing p-0.5"
                  aria-label="Drag handle"
                >
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                    <circle cx="9" cy="5" r="1.5" />
                    <circle cx="15" cy="5" r="1.5" />
                    <circle cx="9" cy="12" r="1.5" />
                    <circle cx="15" cy="12" r="1.5" />
                    <circle cx="9" cy="19" r="1.5" />
                    <circle cx="15" cy="19" r="1.5" />
                  </svg>
                </div>
                <div className="flex-1">{renderItem(item, isDragging)}</div>
              </div>
            </Reorder.Item>
          );
        })}
      </Reorder.Group>
    </div>
  );
}
