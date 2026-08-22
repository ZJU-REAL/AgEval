export {
  BRAND_MARKS,
  BRAND_MARK_IDS,
  matchBrandMarkExact,
  type BrandMarkEntry,
  type BrandMarkKind,
} from "@/lib/brand-marks/catalog";
export { BrandMarkSvg, hasBrandMarkGlyph } from "@/lib/brand-marks/marks";
export {
  resolveEntityMark,
  resolveMechanismMark,
  type EntityMarkHint,
  type ResolvedMark,
} from "@/lib/brand-marks/resolve";
export { entityHintFromPackage, markFromPackage } from "@/lib/brand-marks/from-package";
