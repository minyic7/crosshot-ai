import { type InputHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
}

export function Input({ className, label, id, ...props }: InputProps) {
  return (
    <div className="form-group">
      {label && <label htmlFor={id} className="form-label">{label}</label>}
      <input id={id} className={cn('form-input', className)} {...props} />
    </div>
  )
}
