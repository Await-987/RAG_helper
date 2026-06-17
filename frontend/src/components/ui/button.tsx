import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-2xl text-sm font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/30 disabled:pointer-events-none disabled:opacity-50 active:scale-[0.97]",
  {
    variants: {
      variant: {
        default:
          "bg-primary-600 text-white shadow-lg shadow-primary-600/20 hover:bg-primary-700 hover:shadow-xl hover:shadow-primary-600/30 hover:-translate-y-px",
        destructive:
          "bg-red-600 text-white shadow-lg shadow-red-600/20 hover:bg-red-700 hover:shadow-xl hover:shadow-red-600/30 hover:-translate-y-px",
        outline:
          "border border-white/[0.08] bg-zinc-800/50 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 hover:border-white/[0.12]",
        secondary:
          "bg-zinc-800/50 text-zinc-300 border border-white/[0.08] hover:bg-zinc-700/50 hover:text-zinc-100",
        ghost:
          "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200",
        link:
          "text-primary-400 underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2.5",
        sm: "h-8 rounded-xl px-3 text-xs",
        lg: "h-12 rounded-2xl px-6",
        icon: "h-9 w-9 rounded-xl",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
