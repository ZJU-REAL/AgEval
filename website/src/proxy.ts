import { createI18nMiddleware } from "fumadocs-core/i18n/middleware";
import { i18n } from "@/lib/i18n";

/**
 * Keeps every public page under an explicit locale prefix. Fumadocs owns the
 * locale cookie and redirect rules; the docs application does not infer any
 * runtime identity from the request.
 */
export default createI18nMiddleware(i18n);

export const config = {
  matcher: [
    "/((?!api|images|_next/static|_next/image|favicon.ico|favicon.svg|robots.txt).*)",
  ],
};
