import * as CheckboxPrimitive from '@radix-ui/react-checkbox'
import * as SwitchPrimitive from '@radix-ui/react-switch'
import { Check, ChevronDown, Minus } from 'lucide-react'
import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const control =
  'w-full rounded-md border border-line-strong bg-surface px-2.5 text-[13px] text-fg placeholder:text-muted ' +
  'focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-[var(--focus)] disabled:opacity-60'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...p }, ref) {
  return <input ref={ref} className={cn(control, 'h-8', className)} {...p} />
})

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className, ...p },
  ref,
) {
  return <textarea ref={ref} className={cn(control, 'min-h-20 py-2 leading-relaxed', className)} {...p} />
})

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...p },
  ref,
) {
  return (
    <div className={cn('relative', className)}>
      <select ref={ref} className={cn(control, 'h-8 appearance-none pr-8')} {...p}>
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute top-1/2 right-2 size-4 -translate-y-1/2 text-muted" aria-hidden />
    </div>
  )
})

export function Label({ htmlFor, children, className }: { htmlFor?: string; children: ReactNode; className?: string }) {
  return (
    <label htmlFor={htmlFor} className={cn('block text-[13px] font-medium text-fg-2', className)}>
      {children}
    </label>
  )
}

export function Field({
  label,
  help,
  error,
  children,
  className,
  id,
}: {
  label: ReactNode
  help?: ReactNode
  error?: string | null
  children: (id: string) => ReactNode
  className?: string
  id?: string
}) {
  const auto = useId()
  const fid = id ?? auto
  return (
    <div className={cn('space-y-1', className)}>
      <Label htmlFor={fid}>{label}</Label>
      {children(fid)}
      {help && !error && <p className="text-xs text-muted">{help}</p>}
      {error && (
        <p className="text-xs text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

export function Checkbox({
  checked,
  onCheckedChange,
  id,
  disabled,
  className,
  'aria-label': ariaLabel,
}: {
  checked: boolean | 'indeterminate'
  onCheckedChange: (v: boolean) => void
  id?: string
  disabled?: boolean
  className?: string
  'aria-label'?: string
}) {
  return (
    <CheckboxPrimitive.Root
      id={id}
      checked={checked}
      disabled={disabled}
      aria-label={ariaLabel}
      onCheckedChange={(v) => onCheckedChange(v === true)}
      className={cn(
        'flex size-4 shrink-0 items-center justify-center rounded-[3px] border border-line-strong bg-surface',
        'data-[state=checked]:border-accent data-[state=checked]:bg-accent data-[state=checked]:text-accent-fg',
        'data-[state=indeterminate]:border-accent data-[state=indeterminate]:bg-accent data-[state=indeterminate]:text-accent-fg',
        'disabled:opacity-50',
        className,
      )}
    >
      <CheckboxPrimitive.Indicator>
        {checked === 'indeterminate' ? <Minus className="size-3" strokeWidth={3} /> : <Check className="size-3" strokeWidth={3} />}
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export function CheckRow({
  checked,
  onChange,
  label,
  description,
  disabled,
  className,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: ReactNode
  description?: ReactNode
  disabled?: boolean
  className?: string
}) {
  const id = useId()
  return (
    <div className={cn('flex items-start gap-2.5 py-1', disabled && 'opacity-60', className)}>
      <Checkbox id={id} checked={checked} onCheckedChange={onChange} disabled={disabled} className="mt-0.5" />
      <label htmlFor={id} className="min-w-0 cursor-pointer text-[13px] leading-snug">
        <span className="text-fg">{label}</span>
        {description && <span className="block text-xs text-muted">{description}</span>}
      </label>
    </div>
  )
}

export function Switch({
  checked,
  onCheckedChange,
  id,
  disabled,
}: {
  checked: boolean
  onCheckedChange: (v: boolean) => void
  id?: string
  disabled?: boolean
}) {
  return (
    <SwitchPrimitive.Root
      id={id}
      checked={checked}
      disabled={disabled}
      onCheckedChange={onCheckedChange}
      className="relative h-[18px] w-8 shrink-0 rounded-full border border-line-strong bg-surface-3 transition-colors data-[state=checked]:border-accent data-[state=checked]:bg-accent disabled:opacity-50"
    >
      <SwitchPrimitive.Thumb className="block size-3.5 translate-x-0.5 rounded-full bg-surface shadow-sm transition-transform data-[state=checked]:translate-x-[15px]" />
    </SwitchPrimitive.Root>
  )
}

export function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  label,
  size = 'md',
}: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: ReactNode }[]
  label: string
  size?: 'sm' | 'md'
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line-strong bg-surface-2 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            'rounded-[3px] font-medium text-fg-2 transition-colors',
            size === 'sm' ? 'h-6 px-2 text-xs' : 'h-7 px-3 text-[13px]',
            value === o.value ? 'bg-surface text-fg shadow-[0_0_0_1px_var(--border-strong)]' : 'hover:text-fg',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
