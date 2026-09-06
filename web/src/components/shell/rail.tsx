"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { MeuxeMark } from "@/components/ui/mascot";
import { IconButton, iconButtonClassName } from "@/components/ui/icon-button";
import {
  IconQueue,
  IconCompass,
  IconCalendar,
  IconActivity,
  IconSettings,
  IconPosts,
} from "@/components/ui/icons";

const navItems = [
  { href: "/queue", label: "Queue", icon: IconQueue },
  { href: "/discover", label: "Discover", icon: IconCompass },
  { href: "/posts", label: "Posts", icon: IconPosts },
  { href: "/schedule", label: "Schedule", icon: IconCalendar },
  { href: "/activity", label: "Activity", icon: IconActivity },
];

export function Rail({ onSettingsOpen }: { onSettingsOpen: () => void }) {
  const pathname = usePathname();

  return (
    <nav
      className="flex h-full w-16 shrink-0 flex-col items-center bg-well py-3 squircle rounded-panel"
      aria-label="Main navigation"
    >
      <Link href="/queue" className="mb-6" aria-label="Reddit Copilot home">
        <MeuxeMark size={48} />
      </Link>

      <div className="flex flex-1 flex-col items-center gap-1">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active =
            pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              aria-label={label}
              title={label}
              className={iconButtonClassName({
                active,
                className: cn(active && "text-ink"),
              })}
            >
              <Icon size={20} />
            </Link>
          );
        })}
      </div>

      <IconButton label="Settings" onClick={onSettingsOpen}>
        <IconSettings size={20} />
      </IconButton>
    </nav>
  );
}
