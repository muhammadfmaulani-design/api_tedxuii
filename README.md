# TEDxUII Ticketing API 🚀

Sistem backend untuk manajemen tiket TEDxUII menggunakan FastAPI, Supabase, dan Midtrans.

## Fitur
- Pemesanan tiket terintegrasi Midtrans.
- Otomatisasi generate QR Code ke desain tiket.
- Penyimpanan tiket di Supabase Storage.
- Pengiriman tiket otomatis via Email.

## Cara Menjalankan
1. Install dependensi: `pip install -r requirements.txt`
2. Pastikan file `.env` sudah terisi.
3. Jalankan server: `uvicorn app.main:app --reload`
4. Buka dokumentasi API di: `http://localhost:8000/docs`

## Catatan Desain
Taruh file desain tiket di: `app/static/templates/desain_tiket.jpg`