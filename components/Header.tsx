"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { signIn, signOut, useSession } from "next-auth/react";
import { Box, LogOut, Sparkles } from "lucide-react";
import { getTriposrDisplayHost } from "@/lib/triposr-display";

const glassHeader =
  "sticky top-0 z-50 border-b border-white/[0.08] bg-[#121214]/55 shadow-[0_8px_40px_rgba(0,0,0,0.55)] backdrop-blur-2xl";

const neonRing =
  "shadow-[0_0_28px_rgba(0,229,255,0.35),0_0_60px_rgba(0,229,255,0.12)]";

export function Header() {
  const pathname = usePathname();
  const { data: session, status } = useSession();
  const onGenerate = pathname?.startsWith("/generate");

  return (
    <header className={`${glassHeader} shrink-0`}>
      <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between px-4 sm:h-16 sm:px-6 lg:px-8">
        <Link href="/" className="group flex items-center gap-3">
          <div
            className={`flex h-9 w-9 items-center justify-center rounded-xl border border-[#00E5FF]/40 bg-[#00E5FF]/10 transition group-hover:border-[#00E5FF]/60 ${neonRing}`}
          >
            <Sparkles className="h-4 w-4 text-[#00E5FF]" strokeWidth={1.75} />
          </div>
          <div className="flex flex-col leading-tight">
            <span className="font-display text-lg font-semibold tracking-tight text-white sm:text-xl">
              Origin Real
            </span>
            <span className="hidden text-[10px] font-medium uppercase tracking-[0.22em] text-zinc-500 sm:block">
              AI 3D Studio
            </span>
          </div>
        </Link>

        <div className="flex items-center gap-2 sm:gap-3">
          {onGenerate ? (
            <span className="hidden rounded-full border border-[#00E5FF]/20 bg-[#00E5FF]/[0.06] px-3 py-1 text-[11px] text-[#00E5FF]/90 shadow-[0_0_20px_rgba(0,229,255,0.12)] backdrop-blur-md md:inline">
              Engine · {getTriposrDisplayHost()}
            </span>
          ) : null}

          {status === "loading" ? (
            <div className="h-9 w-24 animate-pulse rounded-full bg-white/10" />
          ) : session?.user ? (
            <div className="flex items-center gap-2 sm:gap-3">
              <Link
                href="/generate"
                className="hidden items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.06] px-3 py-2 text-xs font-medium text-zinc-200 backdrop-blur-md transition hover:border-[#00E5FF]/30 hover:text-white sm:inline-flex"
              >
                <Box className="h-3.5 w-3.5 text-[#00E5FF]" strokeWidth={2} />
                스튜디오
              </Link>
              {session.user.image ? (
                <Image
                  src={session.user.image}
                  alt={session.user.name ? `${session.user.name} 프로필` : "프로필"}
                  width={36}
                  height={36}
                  className="h-9 w-9 rounded-full border border-[#00E5FF]/30 object-cover shadow-[0_0_20px_rgba(0,229,255,0.2)]"
                  unoptimized
                />
              ) : (
                <div className="flex h-9 w-9 items-center justify-center rounded-full border border-[#00E5FF]/30 bg-zinc-800 text-xs text-zinc-400">
                  ?
                </div>
              )}
              <button
                type="button"
                onClick={() => void signOut({ callbackUrl: "/" })}
                className="inline-flex items-center gap-1.5 rounded-full border border-white/12 bg-white/[0.05] px-3 py-2 text-xs font-medium text-zinc-200 backdrop-blur-md transition hover:border-red-400/30 hover:bg-red-500/10 hover:text-red-200"
              >
                <LogOut className="h-3.5 w-3.5" strokeWidth={2} />
                <span className="hidden sm:inline">로그아웃</span>
              </button>
            </div>
          ) : (
            <>
              <button
                type="button"
                onClick={() => void signIn("google", { callbackUrl: pathname ?? "/" })}
                className="rounded-full border border-white/15 bg-transparent px-4 py-2 text-xs font-semibold text-zinc-200 transition hover:border-white/25 hover:bg-white/[0.05] hover:text-white sm:text-sm"
              >
                로그인
              </button>
              <Link
                href="/generate"
                className="rounded-full border border-[#00E5FF]/45 bg-[#00E5FF]/15 px-4 py-2 text-xs font-semibold text-[#00E5FF] shadow-[0_0_24px_rgba(0,229,255,0.2)] backdrop-blur-md transition hover:bg-[#00E5FF]/25 hover:text-white sm:text-sm"
              >
                무료로 시작하기
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
