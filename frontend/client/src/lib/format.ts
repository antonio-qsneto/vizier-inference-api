export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "N/A";
  }

  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatRelativeCount(value: number | null | undefined, singular: string, plural: string) {
  if (value == null) {
    return "N/A";
  }

  return `${value} ${value === 1 ? singular : plural}`;
}

export function formatPercentage(value: number | null | undefined) {
  if (value == null) {
    return "0%";
  }

  return `${value.toFixed(value >= 10 ? 0 : 1)}%`;
}

export function titleCase(value: string | null | undefined) {
  if (!value) {
    return "N/A";
  }

  return value
    .replace(/[_-]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}
