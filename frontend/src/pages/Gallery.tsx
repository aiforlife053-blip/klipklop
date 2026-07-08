export default function Gallery() {
  return (
    <div className="p-6 space-y-7 bg-muted flex-1 h-[calc(100vh-53px)] overflow-auto" style={{ backgroundImage: 'radial-gradient(rgba(0, 0, 0, 0.05) 1.5px, transparent 1.5px)', backgroundSize: '20px 20px', backgroundPosition: '10px 10px' }}>
      <section className="bg-transparent min-h-[460px] flex flex-col gap-6 w-full">
        <div>
          <h2 className="text-[20px] font-semibold text-black mb-0.5 tracking-tight">Galeri</h2>
          <p className="text-[13px] text-gray-500">Klip yang sudah kamu simpan.</p>
        </div>
        <div className="p-12 border border-dashed border-gray-300 rounded-2xl flex flex-col items-center justify-center text-center bg-white">
          <h3 className="text-[16px] font-semibold text-gray-700 mb-1">Galeri Kosong</h3>
          <p className="text-[13px] text-gray-500">Belum ada klip yang disimpan. (Fitur sedang dimigrasi ke React)</p>
        </div>
      </section>
    </div>
  );
}
