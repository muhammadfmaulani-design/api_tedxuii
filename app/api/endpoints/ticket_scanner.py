from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.supabase import supabase

router = APIRouter()

# Schema (Model) untuk menerima data dari Frontend Scanner
class ScanRequest(BaseModel):
    ticket_code: str
    scan_mode: int  # 1 = Check-in Pagi, 2 = Check-in Siang, 3 = Klaim Sertif/Merch

@router.post("/scan")
async def scan_ticket(request: ScanRequest):
    """
    Endpoint untuk aplikasi Scanner Panitia dengan Konsep 3 Tiket.
    """
    try:
        # 1. CARI TIKET BESERTA DATA ORDER DAN KATEGORINYA SEKALIGUS
        res = supabase.table("tickets").select(
            "*, orders(*, ticket_categories(name))" # Ambil 'name' dari kategori, bukan 'price'
        ).eq("ticket_code", request.ticket_code).execute()

        # Jika array data kosong, berarti tiket palsu/typo
        if not res.data:
            return {
                "status": "error",
                "ui_color": "red",
                "message": "Akses Ditolak! Tiket tidak ditemukan / Palsu."
            }

        # 2. EKSTRAK DATA
        ticket_data = res.data[0]
        order_data = ticket_data.get("orders")
        
        if not order_data:
            return {"status": "error", "ui_color": "red", "message": "Data pesanan rusak."}

        peserta_name = order_data.get("full_name", "Peserta")
        peserta_email = order_data.get("email", "")
        
        # Ambil NAMA kategori tiket
        category_data = order_data.get("ticket_categories")
        ticket_type = category_data.get("name", "").upper() if category_data else ""
        
        # Identifikasi jenis tiket berdasarkan kata kuncinya
        is_morning = "MORNING" in ticket_type
        is_afternoon = "AFTERNOON" in ticket_type
        is_full = "FULL" in ticket_type

        # ==========================================
        # 3. LOGIKA BERDASARKAN MODE SCAN
        # ==========================================
        
        # MODE 1: CHECK-IN MORNING (Sesi Pagi)
        # Yang boleh masuk: MORNING & FULL SESSION
        if request.scan_mode == 1:
            if not (is_morning or is_full):
                return {
                    "status": "error",
                    "ui_color": "red",
                    "message": f"DITOLAK!\nMaaf {peserta_name}, tiket Anda ({ticket_type}) HANYA untuk sesi Siang."
                }

            # Cek apakah sudah check-in?
            if ticket_data.get("is_used") == True:
                return {
                    "status": "warning",
                    "ui_color": "yellow",
                    "message": f"PERHATIAN!\nTiket {peserta_name} SUDAH DIGUNAKAN sebelumnya pada {ticket_data.get('checkin_at')}"
                }

            # Update status check-in
            supabase.table("tickets").update({
                "is_used": True,
                "checkin_at": "now()" 
            }).eq("ticket_code", request.ticket_code).execute()

            return {
                "status": "success",
                "ui_color": "green",
                "message": f"VALID - Sesi Pagi!\nNama: {peserta_name}\n({ticket_type})",
                "peserta": peserta_name
            }

        # MODE 2: CHECK-IN AFTERNOON (Sesi Siang)
        # Yang boleh masuk: AFTERNOON & FULL SESSION
        elif request.scan_mode == 2:
            if not (is_afternoon or is_full):
                return {
                    "status": "error",
                    "ui_color": "red",
                    "message": f"DITOLAK!\nMaaf {peserta_name}, tiket Anda ({ticket_type}) HANYA untuk sesi Pagi."
                }

            # Khusus Afternoon Ticket, kita tandai is_used jika dia belum check-in
            # (Jika Full Session, is_used mungkin sudah True dari pagi, biarkan saja)
            if is_afternoon and ticket_data.get("is_used") == True:
                 return {
                    "status": "warning",
                    "ui_color": "yellow",
                    "message": f"PERHATIAN!\nTiket Afternoon {peserta_name} SUDAH DIGUNAKAN."
                }
                 
            if is_afternoon:
                 supabase.table("tickets").update({
                    "is_used": True,
                    "checkin_at": "now()" 
                }).eq("ticket_code", request.ticket_code).execute()

            return {
                "status": "success",
                "ui_color": "green",
                "message": f"VALID - Sesi Siang!\nNama: {peserta_name}\n({ticket_type})",
                "peserta": peserta_name
            }

        # MODE 3: KLAIM SERTIFIKAT / MERCHANDISE
        # Yang boleh klaim: HANYA FULL SESSION (berdasarkan desain React UI kamu)
        elif request.scan_mode == 3:
            if not is_full:
                return {
                    "status": "error",
                    "ui_color": "red",
                    "message": f"DITOLAK!\nMaaf {peserta_name}, tiket {ticket_type} tidak mendapatkan Merchandise/Sertifikat."
                }

            # Cek double claim
            cek_klaim = supabase.table("klaim_sertifikat").select("id").eq("ticket_code", request.ticket_code).execute()
            
            if cek_klaim.data:
                return {
                    "status": "warning", 
                    "ui_color": "yellow",
                    "message": f"PERINGATAN!\nMerch/Sertifikat atas nama {peserta_name} SUDAH PERNAH DIKLAIM."
                }

            # Simpan ke tabel klaim_sertifikat
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
                    "message": f"KLAIM SUKSES!\nBerikan Merchandise & Sertifikat kepada:\n{peserta_name}",
                    "peserta": peserta_name
                }
            else:
                raise HTTPException(status_code=500, detail="Gagal menyimpan ke database.")

        else:
            return {"status": "error", "ui_color": "red", "message": "Mode Scan tidak valid."}

    except Exception as e:
        print(f"Scanner Error: {e}")
        return {"status": "error", "ui_color": "red", "message": f"Terjadi kesalahan server: {str(e)}"}