import { notFound } from "next/navigation";
import { WeekView } from "@/components/WeekView";
import { formatWeek, listWeeks, readWeek } from "@/lib/weeks";

// Next.js 15: params는 Promise다.
type Params = Promise<{ week: string }>;

// 발행된 주차만 페이지가 된다. 그 외 주차는 404 (정적 내보내기라 런타임 폴백이 없다).
export const dynamicParams = false;

export function generateStaticParams() {
  return listWeeks().map((week) => ({ week }));
}

export async function generateMetadata({ params }: { params: Params }) {
  const { week } = await params;
  return { title: formatWeek(week) };
}

export default async function WeekPage({ params }: { params: Params }) {
  const { week } = await params;
  const data = readWeek(week);
  if (!data) notFound();
  return <WeekView data={data} weeks={listWeeks()} />;
}
