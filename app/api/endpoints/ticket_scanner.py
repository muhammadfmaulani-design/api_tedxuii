from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.supabase import supabase

router = APIRouter()

# Schema (Model) untuk menerima data dari Frontend Scanner
class ScanRequest(BaseModel):
    ticket_code: str
    scan_mode: int  # 1 = Check-in Pagi, 2 = Check-in Sesi 2, 3 = Klaim Sertif

@router.post("/scan")
async def scan_ticket(request: ScanRequest):
    """
    Endpoint untuk aplikasi Scanner Panitia.
    """
    try:
        # 1. CARI TIKET BESERTA DATA ORDER DAN KATEGORINYA SEKALIGUS
        # Sintaks Supabase ini otomatis melakukan "JOIN" ke tabel orders dan ticket_categories
        res = supabase.table("tickets").select(
            "*, orders(*, ticket_categories(price))"
        ).eq("ticket_code", request.ticket_code).execute()

        # Jika array data kosong, berarti tiket palsu/typo
        if not res.data:
            return {
                "status": "error",
                "ui_color": "red",
                "message": "Akses Ditolak! Tiket tidak ditemukan / Tidak Valid."
            }

        # 2. EKSTRAK DATA
        ticket_data = res.data[0]
        order_data = ticket_data.get("orders")
        
        if not order_data:
            return {"status": "error", "ui_color": "red", "message": "Data pesanan rusak."}

        peserta_name = order_data.get("full_name", "Peserta")
        peserta_email = order_data.get("email", "")
        
        # Ambil harga tiket untuk menentukan dia VIP (50k) atau Reguler (25k)
        category_data = order_data.get("ticket_categories")
        ticket_price = category_data.get("price", 0) if category_data else 0
        
        is_vip = ticket_price >= 50000

        # ==========================================
        # 3. LOGIKA BERDASARKAN MODE SCAN
        # ==========================================
        
        # MODE 1: Pintu Masuk Pagi (Semua boleh masuk)
        if request.scan_mode == 1:
            tipe = "Full Session (VIP)" if is_vip else "Sesi 1 Saja (Reguler)"
            return {
                "status": "success",
                "ui_color": "green",
                "message": f"Tiket Valid!\nNama: {peserta_name}\nTipe: {tipe}",
                "peserta": peserta_name
            }

        # MODE 2: Pintu Masuk Sesi 2 (Filter VIP saja)
        elif request.scan_mode == 2:
            if is_vip:
                return {
                    "status": "success",
                    "ui_color": "green",
                    "message": f"Akses Sesi 2 Diberikan.\nNama: {peserta_name}",
                    "peserta": peserta_name
                }
            else:
                return {
                    "status": "error",
                    "ui_color": "red",
                    "message": f"Akses Ditolak!\nMaaf {peserta_name}, tiket Anda hanya untuk Sesi 1."
                }

        # MODE 3: Pintu Keluar / Klaim Sertifikat (Filter VIP & Simpan Database)
        elif request.scan_mode == 3:
            if not is_vip:
                return {
                    "status": "error",
                    "ui_color": "red",
                    "message": f"Gagal Klaim!\n{peserta_name} tidak memiliki fasilitas Sertifikat."
                }

            # Cek dulu, apakah dia sudah pernah scan keluar sebelumnya? (Mencegah double claim)
            cek_klaim = supabase.table("klaim_sertifikat").select("id").eq("ticket_code", request.ticket_code).execute()
            
            if cek_klaim.data:
                return {
                    "status": "warning", 
                    "ui_color": "yellow", # Warna kuning untuk "Sudah Pernah"
                    "message": f"Peringatan!\nSertifikat atas nama {peserta_name} SUDAH DIKLAIM sebelumnya."
                }

            # Jika belum pernah, masukkan ke tabel klaim_sertifikat
            klaim_payload = {
                "ticket_code": request.ticket_code,
                "nama_peserta": peserta_name,
                "email_peserta": peserta_email
            }
            insert_res = supabase.table("klaim_sertifikat").insert(klaim_payload).execute()

            if insert_res.data:
                return {
                    "status": "success",
                    "ui_color": "green",
                    "message": f"Klaim Sukses!\nData {peserta_name} berhasil direkam untuk e-Sertifikat. Boleh pulang.",
                    "peserta": peserta_name
                }
            else:
                raise HTTPException(status_code=500, detail="Gagal menyimpan ke database.")

        else:
            return {"status": "error", "ui_color": "red", "message": "Mode Scan tidak dikenali."}

    except Exception as e:
        print(f"Scanner Error: {e}")
        return {"status": "error", "ui_color": "red", "message": f"Terjadi kesalahan server: {str(e)}"}