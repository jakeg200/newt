import type { Metadata } from "next";
import { Bricolage_Grotesque, Caveat, Geist, Geist_Mono } from "next/font/google";
import { AuthGate } from "@/components/AuthGate";
import { Header } from "@/components/Header";
import { BRAND } from "@/lib/brand";
import { UserProvider } from "@/lib/user";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const bricolage = Bricolage_Grotesque({ variable: "--font-bricolage", subsets: ["latin"], weight: ["600", "800"] });
const caveat = Caveat({ variable: "--font-caveat", subsets: ["latin"], weight: ["600", "700"] });

export const metadata: Metadata = {
  title: BRAND,
  description: "Onboard AI agents like new hires, and prove what they can be trusted with.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} ${bricolage.variable} ${caveat.variable} font-sans antialiased`}>
        <UserProvider>
          <Header />
          <main className="mx-auto max-w-6xl px-4 pb-16 pt-6 sm:px-6">
            <AuthGate>{children}</AuthGate>
          </main>
        </UserProvider>
      </body>
    </html>
  );
}
