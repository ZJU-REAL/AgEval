"use client";

import { use, useMemo } from "react";
import { create } from "@orama/orama";
import { useDocsSearch } from "fumadocs-core/search/client";
import { useI18n } from "fumadocs-ui/contexts/i18n";
import { siteBasePath } from "@/lib/shared";
import {
  SearchDialog,
  SearchDialogClose,
  SearchDialogContent,
  SearchDialogHeader,
  SearchDialogIcon,
  SearchDialogInput,
  SearchDialogList,
  SearchDialogOverlay,
  type SharedProps,
} from "fumadocs-ui/components/dialog/search";

const staticClient = import("fumadocs-core/search/client/orama-static");

function initOrama() {
  return create({ schema: { _: "string" } });
}

/**
 * Client-side Orama over the exported index. Default Fumadocs static
 * client passes `language: locale`, and Orama rejects `zh-CN`.
 */
export function StaticSearchDialog(props: SharedProps) {
  const { locale } = useI18n();
  const { oramaStaticClient } = use(staticClient);
  const client = useMemo(
    () =>
      oramaStaticClient({
        locale,
        initOrama,
        from: `${siteBasePath()}/search-index.json`,
      }),
    [locale, oramaStaticClient],
  );
  const { search, setSearch, query } = useDocsSearch({ client });

  return (
    <SearchDialog
      search={search}
      onSearchChange={setSearch}
      isLoading={query.isLoading}
      {...props}
    >
      <SearchDialogOverlay />
      <SearchDialogContent>
        <SearchDialogHeader>
          <SearchDialogIcon />
          <SearchDialogInput />
          <SearchDialogClose />
        </SearchDialogHeader>
        <SearchDialogList items={query.data !== "empty" ? query.data : null} />
      </SearchDialogContent>
    </SearchDialog>
  );
}
