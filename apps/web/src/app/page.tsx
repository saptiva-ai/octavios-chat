"use client";

import Image from "next/image";
import Link from "next/link";

export default function HomePage() {
  const primaryCtaHref = "/login";
  const primaryCtaLabel = "Iniciar sesión";
  const secondaryCtaHref = "/register";
  const secondaryCtaLabel = "Crear cuenta";

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-x-hidden bg-background px-4 py-12 text-foreground">
      <div className="mx-auto flex w-full max-w-md flex-col items-center text-center">
        {/* Logo OctaviOS - Theme Aware */}
        <div className="mb-12 flex flex-col items-center">
          <div className="relative h-48 w-48">
            {/* Light theme logo - hidden in dark mode */}
            <Image
              src="/OctaviOS_WhiteBack2.png"
              alt="OctaviOS Chat"
              fill
              priority
              sizes="192px"
              className="object-contain drop-shadow-[0_10px_30px_rgba(73,247,217,0.45)] dark:hidden"
            />
            {/* Dark theme logo - hidden in light mode */}
            <Image
              src="/OctaviOS_DarkBack2.png"
              alt="OctaviOS Chat"
              fill
              priority
              sizes="192px"
              className="object-contain drop-shadow-[0_10px_30px_rgba(73,247,217,0.45)] hidden dark:block"
            />
          </div>
        </div>

        {/* CTAs */}
        <div className="flex w-full flex-col gap-3 sm:flex-row sm:justify-center">
          <Link
            href={primaryCtaHref}
            className="inline-flex items-center justify-center rounded-lg bg-primary px-8 py-3.5 text-base font-semibold text-white shadow-sm transition-colors duration-200 hover:bg-primary-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            aria-label="Iniciar sesión en OctaviOS Chat"
          >
            {primaryCtaLabel}
          </Link>
          <Link
            href={secondaryCtaHref}
            className="inline-flex items-center justify-center rounded-lg border border-border bg-surface px-8 py-3.5 text-base font-medium text-foreground shadow-sm transition-colors duration-200 hover:bg-surface-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            aria-label="Crear cuenta en OctaviOS Chat"
          >
            {secondaryCtaLabel}
          </Link>
        </div>

        {/* Footer */}
        <footer className="mt-16">
          <p className="text-sm text-muted">
            Plataforma desarrollada por Saptiva Inc.
          </p>
        </footer>
      </div>
    </div>
  );
}
