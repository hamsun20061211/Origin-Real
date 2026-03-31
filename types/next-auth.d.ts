import type { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    user?: DefaultSession["user"] & { image?: string | null };
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    picture?: string;
  }
}
