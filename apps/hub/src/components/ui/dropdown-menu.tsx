import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import * as React from "react";

import { useOverlayRoot } from "@/components/overlay-root";
import { cn } from "@/lib/utils";

export const DropdownMenu = DropdownMenuPrimitive.Root;
export const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger;

export const DropdownMenuContent = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Content>
>(({ className, sideOffset = 6, ...props }, ref) => {
  const container = useOverlayRoot();
  return (
  <DropdownMenuPrimitive.Portal container={container}>
    <DropdownMenuPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      data-ageval-menu=""
      className={cn(
        "z-[70] min-w-[8rem] overflow-hidden rounded-[8px] border border-hairline bg-canvas p-1 text-ink shadow-[var(--viewer-shadow-pop)]",
        className,
      )}
      {...props}
    />
  </DropdownMenuPrimitive.Portal>
  );
});
DropdownMenuContent.displayName = DropdownMenuPrimitive.Content.displayName;

export const DropdownMenuItem = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Item>
>(({ className, ...props }, ref) => (
  <DropdownMenuPrimitive.Item
    ref={ref}
    className={cn(
      "relative flex cursor-pointer select-none items-center gap-2 rounded-[6px] px-2 py-1.5 text-sm outline-none transition-colors duration-200 ease-smooth data-[highlighted]:bg-canvas-soft focus:bg-canvas-soft data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      className,
    )}
    {...props}
  />
));
DropdownMenuItem.displayName = DropdownMenuPrimitive.Item.displayName;

export const DropdownMenuSeparator = React.forwardRef<
  React.ElementRef<typeof DropdownMenuPrimitive.Separator>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Separator>
>(({ className, ...props }, ref) => (
  <DropdownMenuPrimitive.Separator
    ref={ref}
    className={cn("-mx-1 my-1 h-px bg-hairline", className)}
    {...props}
  />
));
DropdownMenuSeparator.displayName =
  DropdownMenuPrimitive.Separator.displayName;
