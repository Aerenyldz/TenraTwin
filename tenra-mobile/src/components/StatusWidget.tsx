import React, { useEffect, useRef, useState } from 'react';
import { fetchStatus, updateStatus } from '../api';

const STATUS_DETAILS: Record<string, string> = {
  Okulda: 'Ahmet şu an derste, önemli bir şey varsa not alıyorum.',
  Sporda: 'Ahmet sporda, antrenman bitince arar. Not bırakayım mı?',
  Toplantıda: 'Toplantıdayım, acil değilse mesaj bırakın.',
  Müsait: 'Ahmet müsait, telefonu kendisine aktarıyorum.',
  Yemekte: 'Ahmet şu an yemekte, bitince döner. Not bırakmak ister misin?',
  Uykuda: 'Ahmet uyuyor, acil değilse uyandığında döner sana.',
  Trafikte: 'Ahmet trafikte, varınca arar. Bir şey ileteyim mi?',
  Dışarıda: 'Ahmet dışarıda, eve dönünce döner sana. Not bırakayım mı?',
  'Ders Çalışıyorum': 'Ahmet ders çalışıyor, mola verince döner. Not alsın mı?'
};

const OPTIONS = [
  { id: 'Okulda', icon: '🎓', label: 'Okulda' },
  { id: 'Sporda', icon: '🏋️‍♂️', label: 'Sporda' },
  { id: 'Toplantıda', icon: '💼', label: 'Toplantı' },
  { id: 'Müsait', icon: '🟢', label: 'Müsait' },
  { id: 'Yemekte', icon: '🍽️', label: 'Yemekte' },
  { id: 'Uykuda', icon: '😴', label: 'Uykuda' },
  { id: 'Trafikte', icon: '🚗', label: 'Trafikte' },
  { id: 'Dışarıda', icon: '🏖️', label: 'Dışarıda' },
  { id: 'Ders Çalışıyorum', icon: '📚', label: 'Ders' }
];

const CUSTOM_ID = '__custom__';

export const StatusWidget: React.FC = () => {
  const [currentStatus, setCurrentStatus] = useState<string>('Okulda');
  const [currentDetail, setCurrentDetail] = useState<string>(STATUS_DETAILS['Okulda']);
  const [customNote, setCustomNote] = useState<string>('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetchStatus()
      .then((data) => {
        if (data.status) {
          setCurrentStatus(data.status);
          const detail = data.status_detail || STATUS_DETAILS[data.status] || '';
          setCurrentDetail(detail);
          // Eğer DB'deki mod preset listede yoksa özel not modunda aç
          if (!OPTIONS.find(o => o.id === data.status)) {
            setCurrentStatus(CUSTOM_ID);
            setCustomNote(detail);
          }
        }
      })
      .catch(() => {});
  }, []);

  const handleSelect = async (status: string) => {
    if (status === CUSTOM_ID) {
      setCurrentStatus(CUSTOM_ID);
      // Textarea'ya odaklan
      setTimeout(() => textareaRef.current?.focus(), 50);
      return;
    }
    const detail = STATUS_DETAILS[status] || 'Ahmet şu an müsait değil.';
    setCurrentStatus(status);
    setCurrentDetail(detail);
    try {
      await updateStatus(status, detail);
    } catch (err) {
      console.warn('Status update error:', err);
    }
  };

  const handleCustomSave = async () => {
    if (!customNote.trim()) return;
    setSaving(true);
    setSaved(false);
    try {
      setCurrentDetail(customNote.trim());
      await updateStatus('Özel', customNote.trim());
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      console.warn('Custom status save error:', err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="status-widget">
      <div className="status-label">Asistan Çağrı Modu</div>
      <div className="status-pills">
        {OPTIONS.map((opt) => (
          <button
            key={opt.id}
            className={`status-btn ${currentStatus === opt.id ? 'active' : ''}`}
            onClick={() => handleSelect(opt.id)}
          >
            <span style={{ fontSize: '1.25rem' }}>{opt.icon}</span>
            <span>{opt.label}</span>
          </button>
        ))}
        <button
          className={`status-btn ${currentStatus === CUSTOM_ID ? 'active' : ''}`}
          onClick={() => handleSelect(CUSTOM_ID)}
        >
          <span style={{ fontSize: '1.25rem' }}>✏️</span>
          <span>Özel</span>
        </button>
      </div>

      {currentStatus === CUSTOM_ID && (
        <div className="custom-note-area">
          <textarea
            ref={textareaRef}
            className="custom-note-input"
            placeholder="Örn: Şu an veznedeyim, çıkışımda müsaitim. Önemli bir şey varsa not bırakın."
            value={customNote}
            onChange={(e) => setCustomNote(e.target.value)}
            rows={3}
            maxLength={300}
          />
          <div className="custom-note-footer">
            <span className="char-count">{customNote.length}/300</span>
            <button
              className={`save-note-btn ${saved ? 'saved' : ''}`}
              onClick={handleCustomSave}
              disabled={saving || !customNote.trim()}
            >
              {saving ? '⏳ Kaydediliyor…' : saved ? '✅ Kaydedildi' : '💾 Kaydet'}
            </button>
          </div>
          <div className="custom-note-hint">
            🤖 Yapay zeka bu notu analiz edip arayana uygun şekilde özetleyecek.
          </div>
        </div>
      )}

      <div className="status-current-hint">
        ⚡ Aktif Cevap: "{currentDetail}"
      </div>
    </section>
  );
};
