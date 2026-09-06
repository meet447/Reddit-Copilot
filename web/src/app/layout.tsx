import { Figtree, JetBrains_Mono } from "next/font/google";
import "@/index.css";
import { ConditionalShell } from "@/components/shell/conditional-shell";

const figtree = Figtree({
  variable: "--font-figtree",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata = {
  title: "Reddit Copilot",
  description: "Review and approve Reddit replies in your voice.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${figtree.variable} ${jetbrainsMono.variable} h-full`}
    >
      <body className="min-h-full">
        <ConditionalShell>{children}</ConditionalShell>
      </body>
    </html>
  );
}
