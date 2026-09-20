import type { Metadata } from "next";
import "./globals.css";
import "./video.css";

export const metadata: Metadata = {
  title: "DeepGuard AI · Media intelligence",
  description:
    "Inspect image provenance and explore AI-generation signals with transparent, evidence-led analysis.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
