#!/system/bin/sh
# Jadikan HP sebagai keyboard USB (NKRO) lewat OTG/kabel USB ke laptop.
# Syarat: ROOT + kernel HP mendukung USB gadget HID (CONFIG_USB_CONFIGFS_F_HID).
# Jalankan (sebelum buka app, mode "HID root"):
#     su -c "sh /sdcard/setup_hid.sh"
# Setelah selesai, HP tidak lagi MTP/ADB sampai restart atau ganti mode USB.

G=/config/usb_gadget
[ -d $G ] || mount -t configfs none /config 2>/dev/null
cd $G || { echo "configfs usb_gadget tidak ada -> kernel tidak mendukung, pakai mode UDP"; exit 1; }

# matikan gadget bawaan Android
setprop sys.usb.config none 2>/dev/null
for g in */; do echo "" > "${g}UDC" 2>/dev/null; done
sleep 1

mkdir -p osukeys && cd osukeys || exit 1
echo 0x1d6b > idVendor
echo 0x0104 > idProduct
mkdir -p strings/0x409
echo "OsuKeys0001" > strings/0x409/serialnumber
echo "OsuKeys" > strings/0x409/manufacturer
echo "OsuKeys Keyboard" > strings/0x409/product
mkdir -p configs/c.1
mkdir -p functions/hid.usb0
echo 0 > functions/hid.usb0/protocol
echo 0 > functions/hid.usb0/subclass
echo 16 > functions/hid.usb0/report_length

# Report descriptor: 1 byte modifier + bitmap 120 key (NKRO), total 16 byte
printf '\x05\x01\x09\x06\xA1\x01\x05\x07\x19\xE0\x29\xE7\x15\x00\x25\x01\x75\x01\x95\x08\x81\x02\x05\x07\x19\x00\x29\x77\x15\x00\x25\x01\x75\x01\x95\x78\x81\x02\xC0' > functions/hid.usb0/report_desc

ln -s functions/hid.usb0 configs/c.1/ 2>/dev/null
UDC=$(ls /sys/class/udc | head -n1)
echo "$UDC" > UDC

sleep 1
chmod 666 /dev/hidg0 2>/dev/null
ls -l /dev/hidg0 && echo "OK: /dev/hidg0 siap" || echo "GAGAL: /dev/hidg0 tidak muncul"
