import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin", "cyrillic"], variable: "--font-inter" });
const mono = JetBrains_Mono({ subsets: ["latin", "cyrillic"], variable: "--font-jetbrains" });

export const metadata: Metadata = {
  title: "FB Rent — Ops Control Panel",
  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/icon.png", type: "image/png" },
    ],
    apple: [
      { url: "/apple-touch-icon.png" },
    ],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="uk" className={`${inter.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
