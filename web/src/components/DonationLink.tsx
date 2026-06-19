const KOFI_URL = "https://ko-fi.com/davar";

type DonationLinkProps = {
  compact?: boolean;
};

export default function DonationLink({ compact = false }: DonationLinkProps) {
  return (
    <a
      href={KOFI_URL}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center justify-center gap-2 rounded-full border border-[#ff5f5f]/30 bg-[#ff5f5f] px-4 py-2 text-sm font-semibold text-white shadow-card transition hover:bg-[#e34d4d] focus:outline-none focus:ring-2 focus:ring-[#ff5f5f] focus:ring-offset-2 focus:ring-offset-canvas"
      aria-label="Support Nave on Ko-fi"
    >
      <span aria-hidden="true">Ko-fi</span>
      {!compact && <span>Support Nave</span>}
    </a>
  );
}
