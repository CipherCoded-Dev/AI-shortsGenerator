import type { Metadata } from "next";
import { IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const plexMono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Shorts — YouTube to vertical clips",
  description: "Paste a YouTube link and get back cropped, ready-to-post short clips.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${plexMono.variable} h-full antialiased`}>
      <head>
        {/* General Sans — Fontshare, free for commercial use. Swap for a self-hosted
            woff2 in /public/fonts if you want to drop the external request. */}
        <link
          href="https://api.fontshare.com/v2/css?f[]=general-sans@500,600,700,400&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-full flex flex-col bg-[#0A0A0C] text-zinc-100">{children}</body>
    </html>
  );
}