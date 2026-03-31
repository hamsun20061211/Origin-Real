"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Images, Type } from "lucide-react";

const cardBase =
  "group relative flex flex-col overflow-hidden rounded-2xl border border-white/[0.08] bg-[#121214]/50 p-8 shadow-[0_0_0_1px_rgba(255,255,255,0.03)_inset] backdrop-blur-xl transition hover:border-[#00E5FF]/25";

const glow =
  "pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-[#00E5FF]/20 blur-[80px] transition-opacity group-hover:opacity-100 opacity-60";

export function LandingHome() {
  return (
    <div className="relative flex flex-1 flex-col overflow-hidden">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-10%,rgba(0,229,255,0.14),transparent_55%)]" />
      <div className="pointer-events-none absolute bottom-0 left-1/2 h-[min(50vh,420px)] w-[min(90vw,900px)] -translate-x-1/2 rounded-full bg-[#00E5FF]/[0.06] blur-[120px]" />

      <div className="relative mx-auto flex w-full max-w-[1100px] flex-1 flex-col px-4 pb-16 pt-10 sm:px-6 sm:pt-14 lg:px-8 lg:pt-20">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="mx-auto max-w-3xl text-center"
        >
          <p className="mb-4 text-[11px] font-semibold uppercase tracking-[0.35em] text-[#00E5FF]/80">
            Origin Real
          </p>
          <h1 className="font-display text-3xl font-semibold leading-[1.15] tracking-tight text-white sm:text-4xl md:text-5xl lg:text-[3.25rem]">
            무엇이든{" "}
            <span className="bg-gradient-to-r from-[#00E5FF] via-cyan-300 to-[#00E5FF] bg-clip-text text-transparent">
              3D로 생성
            </span>
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-sm leading-relaxed text-zinc-400 sm:text-base">
            다각도 이미지와 텍스트로 프로 퀄리티 에셋을 준비하세요. 로컬 TripoSR 엔진과 PBR 뷰어로 바로
            확인합니다.
          </p>
        </motion.div>

        <div className="mx-auto mt-14 grid w-full max-w-[920px] gap-6 sm:mt-16 md:grid-cols-2">
          <motion.div
            className="h-full min-h-0"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.08, ease: [0.22, 1, 0.36, 1] }}
            whileHover={{ y: -4 }}
            whileTap={{ scale: 0.99 }}
          >
            <Link href="/generate?mode=image" className={`${cardBase} block h-full`}>
              <div className={glow} />
              <div className="relative mb-6 flex h-14 w-14 items-center justify-center rounded-2xl border border-[#00E5FF]/30 bg-[#00E5FF]/10 shadow-[0_0_32px_rgba(0,229,255,0.25)]">
                <Images className="h-7 w-7 text-[#00E5FF]" strokeWidth={1.5} />
              </div>
              <h2 className="relative text-xl font-semibold text-white">Image to 3D</h2>
              <p className="relative mt-2 text-sm leading-relaxed text-zinc-400">
                다각도 사진으로 정밀 생성
              </p>
              <span className="relative mt-8 inline-flex items-center gap-2 text-sm font-semibold text-[#00E5FF]">
                생성 창 열기
                <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
              </span>
            </Link>
          </motion.div>

          <motion.div
            className="h-full min-h-0"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.16, ease: [0.22, 1, 0.36, 1] }}
            whileHover={{ y: -4 }}
            whileTap={{ scale: 0.99 }}
          >
            <Link href="/generate?mode=text" className={`${cardBase} block h-full`}>
              <div className={glow} />
              <div className="relative mb-6 flex h-14 w-14 items-center justify-center rounded-2xl border border-[#00E5FF]/30 bg-[#00E5FF]/10 shadow-[0_0_32px_rgba(0,229,255,0.25)]">
                <Type className="h-7 w-7 text-[#00E5FF]" strokeWidth={1.5} />
              </div>
              <h2 className="relative text-xl font-semibold text-white">Text to 3D</h2>
              <p className="relative mt-2 text-sm leading-relaxed text-zinc-400">
                상상력을 3D 모델로
              </p>
              <span className="relative mt-8 inline-flex items-center gap-2 text-sm font-semibold text-[#00E5FF]">
                텍스트 생성으로 이동
                <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
              </span>
            </Link>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
