import * as Menu from '@radix-ui/react-dropdown-menu'
import { MoreHorizontal } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export interface MenuAction {
  label: string
  icon?: ReactNode
  onSelect: () => void
  danger?: boolean
  disabled?: boolean
}

export function ActionMenu({ actions, label = 'More actions', trigger }: { actions: (MenuAction | 'separator')[]; label?: string; trigger?: ReactNode }) {
  return (
    <Menu.Root>
      <Menu.Trigger asChild>
        {trigger ?? (
          <button
            type="button"
            aria-label={label}
            className="flex size-8 items-center justify-center rounded-md text-muted hover:bg-surface-3 hover:text-fg data-[state=open]:bg-surface-3"
          >
            <MoreHorizontal className="size-4" />
          </button>
        )}
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content align="end" sideOffset={4} className="z-50 min-w-44 rounded-md border border-line bg-surface p-1 shadow-lg">
          {actions.map((a, i) =>
            a === 'separator' ? (
              <Menu.Separator key={i} className="my-1 h-px bg-line" />
            ) : (
              <Menu.Item
                key={a.label}
                disabled={a.disabled}
                onSelect={a.onSelect}
                className={cn(
                  'flex h-8 cursor-default items-center gap-2 rounded-[3px] px-2 text-[13px] outline-none select-none data-[disabled]:opacity-50 data-[highlighted]:bg-surface-3 [&_svg]:size-4 [&_svg]:text-muted',
                  a.danger && 'text-danger [&_svg]:text-danger',
                )}
              >
                {a.icon}
                {a.label}
              </Menu.Item>
            ),
          )}
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  )
}
