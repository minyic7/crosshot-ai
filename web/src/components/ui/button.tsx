import { type ButtonHTMLAttributes } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva('btn', {
  variants: {
    variant: {
      default: 'btn-primary',
      secondary: '',
      ghost: 'btn-ghost',
      outline: 'btn-outline',
    },
    size: {
      default: '',
      sm: 'btn-sm',
      icon: 'btn-icon',
    },
  },
  defaultVariants: {
    variant: 'default',
    size: 'default',
  },
})

interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return (
    <button
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}
