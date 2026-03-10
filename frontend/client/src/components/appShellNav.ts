export interface NavMatchItem {
  href: string;
}

function normalizePath(path: string): string {
  const [withoutQuery] = path.split("?");
  const [withoutHash] = withoutQuery.split("#");
  if (withoutHash.length > 1 && withoutHash.endsWith("/")) {
    return withoutHash.slice(0, -1);
  }
  return withoutHash || "/";
}

export function matchesNavPath(currentPath: string, href: string): boolean {
  const normalizedCurrentPath = normalizePath(currentPath);
  const normalizedHref = normalizePath(href);

  if (normalizedCurrentPath === normalizedHref) {
    return true;
  }

  if (normalizedHref === "/") {
    return normalizedCurrentPath === "/";
  }

  return normalizedCurrentPath.startsWith(`${normalizedHref}/`);
}

export function getActiveNavHref(
  currentPath: string,
  navItems: NavMatchItem[],
): string | null {
  let activeHref: string | null = null;

  for (const item of navItems) {
    if (!matchesNavPath(currentPath, item.href)) {
      continue;
    }

    if (!activeHref || item.href.length > activeHref.length) {
      activeHref = item.href;
    }
  }

  return activeHref;
}
