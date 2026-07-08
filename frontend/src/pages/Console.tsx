export default function Console() {
  return (
    <div className="p-6 space-y-7 bg-muted flex-1 h-[calc(100vh-53px)] overflow-auto" style={{ backgroundImage: 'radial-gradient(rgba(0, 0, 0, 0.05) 1.5px, transparent 1.5px)', backgroundSize: '20px 20px', backgroundPosition: '10px 10px' }}>
      <section className="bg-transparent min-h-[460px] flex flex-col gap-5 w-full">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-[20px] font-semibold text-black mb-0.5 tracking-tight">Konsol</h2>
            <p className="text-[13px] text-gray-500">Log pemrosesan sistem.</p>
          </div>
          <button type="button" className="rounded-xl border border-gray-200 px-4 py-2 text-[13px] font-semibold text-gray-700 hover:bg-gray-50 bg-white">
            Clear
          </button>
        </div>
        <div className="min-h-[360px] max-h-[70vh] overflow-auto rounded-2xl bg-[#f8fafc] border border-gray-200 p-4 font-mono text-[12px] leading-relaxed text-gray-800">
          <p className="text-gray-400 italic">Console output akan muncul di sini... (Fitur sedang dimigrasi)</p>
        </div>
      </section>
    </div>
  );
}
