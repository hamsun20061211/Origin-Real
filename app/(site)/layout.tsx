import { Header } from "@/components/Header";

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-[#050505] text-zinc-100 antialiased">
      <Header />
      {children}
    </div>
  );
}
