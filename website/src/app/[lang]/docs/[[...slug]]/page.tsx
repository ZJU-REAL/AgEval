import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { createRelativeLink } from "fumadocs-ui/mdx";
import { DocsBody, DocsDescription, DocsPage, DocsTitle } from "fumadocs-ui/layouts/docs/page";
import { getMDXComponents } from "@/components/mdx";
import { source } from "@/lib/source";
import { isSiteLocale } from "@/lib/i18n";

type DocsParams = { lang: string; slug?: string[] };

export default async function Page({ params }: { params: Promise<DocsParams> }) {
  const { lang, slug } = await params;
  if (!isSiteLocale(lang)) notFound();

  const page = source.getPage(slug, lang);
  if (!page) notFound();
  const MDX = page.data.body;

  return (
    <DocsPage toc={page.data.toc} full={page.data.full}>
      <DocsTitle className="docs-display-title">{page.data.title}</DocsTitle>
      <DocsDescription>{page.data.description}</DocsDescription>
      <DocsBody className="docs-reading-body">
        <MDX components={getMDXComponents({ a: createRelativeLink(source, page) })} />
      </DocsBody>
    </DocsPage>
  );
}

export function generateStaticParams() {
  return source.generateParams();
}

export async function generateMetadata({
  params,
}: {
  params: Promise<DocsParams>;
}): Promise<Metadata> {
  const { lang, slug } = await params;
  if (!isSiteLocale(lang)) notFound();

  const page = source.getPage(slug, lang);
  if (!page) notFound();
  return { title: page.data.title, description: page.data.description };
}
