# Salawat — 7-image cinematic sequence

A **cinématique islamique, réaliste mais sobre**, avec une continuité visuelle
entre les 7 images. **Aucun visage du Prophète ﷺ ni représentation d'Allah.**

Each section below has a ready-to-paste image prompt. The individual `.txt`
files under [`prompts/`](prompts/) contain the exact same English prompts, one
per file, for easy copy-paste into your image generator.

## Style commun à conserver

> **16:9, cinematic, realistic, soft golden light, spiritual atmosphere,
> subtle volumetric lighting, highly detailed, warm beige and deep blue tones,
> peaceful, respectful Islamic aesthetic, no text, no watermark.**

(Also stored on its own in [`style.txt`](style.txt).)

---

## 1. Introduction — ciel et lumière
`prompts/01_introduction.txt`

```text
A peaceful night sky above an ancient Middle Eastern city, countless stars shining softly, deep blue sky, subtle golden light appearing on the horizon, quiet atmosphere, beautiful Islamic architecture in the distance, cinematic wide shot, gentle mist, spiritual and peaceful mood, realistic cinematic photography, soft volumetric lighting, warm beige and deep blue color palette, highly detailed, 16:9, no people in the foreground, no text, no watermark
```

## 2. « إِنَّ اللَّهَ وَمَلَائِكَتَهُ… »
`prompts/02_inna_allaha.txt`

```text
A majestic symbolic heavenly scene above an ancient peaceful city, soft radiant light descending from the sky through layers of luminous clouds, countless tiny particles of light floating gently in the air, atmosphere suggesting divine mercy and heavenly presence without depicting God or any human figure, deeply spiritual and respectful Islamic aesthetic, cinematic wide composition, realistic lighting, warm golden and deep blue tones, volumetric light rays, highly detailed, 16:9, no human figures, no text, no watermark
```

## 3. « يُصَلُّونَ عَلَى النَّبِيِّ »
`prompts/03_yusalluna.txt`

```text
A serene historical view of ancient Medina at sunset, beautiful early Islamic architecture and a simple mosque in the distance, palm trees gently moving in the evening breeze, golden sunlight illuminating the city, peaceful atmosphere, subtle glowing sky, symbolic spiritual representation, no depiction of Prophet Muhammad, no identifiable religious figure, cinematic wide shot, realistic historical environment, soft volumetric lighting, warm golden and deep blue tones, highly detailed, 16:9, no text, no watermark
```

## 4. « يَا أَيُّهَا الَّذِينَ آمَنُوا… »
`prompts/04_ya_ayyuha.txt`

```text
A diverse group of Muslim believers walking peacefully toward a beautiful mosque at sunset, seen only from behind and mostly as gentle silhouettes, men and women in modest traditional clothing, different ages and backgrounds, warm light surrounding them, feeling of unity and faith, ancient Middle Eastern city environment, cinematic composition, realistic photography, soft golden light, subtle atmospheric haze, respectful Islamic aesthetic, warm beige and deep blue tones, highly detailed, 16:9, no visible faces, no text, no watermark
```

## 5. « صَلُّوا عَلَيْهِ… »
`prompts/05_sallu_alayhi.txt`

```text
A beautifully arranged Quran resting peacefully on a simple wooden stand beside prayer beads on a traditional prayer rug, soft warm sunlight entering through an ornate Islamic window, delicate dust particles floating in the light, peaceful spiritual atmosphere, close cinematic shot, shallow depth of field, realistic textures, elegant Islamic interior, warm golden and deep blue color palette, highly detailed, 16:9, no readable text on the Quran, no watermark
```

## 6. « وَسَلِّمُوا تَسْلِيمًا »
`prompts/06_wa_sallimu.txt`

```text
A magnificent mosque illuminated under a peaceful starry night sky, warm golden lights glowing from the windows and entrance, quiet courtyard, subtle reflections on polished stone, gentle clouds moving across the deep blue sky, atmosphere of peace, blessings and devotion, cinematic wide shot, realistic architecture, soft volumetric moonlight and warm illumination, highly detailed, respectful Islamic aesthetic, 16:9, no people in foreground, no text, no watermark
```

## 7. Conclusion
`prompts/07_conclusion.txt`

```text
A peaceful cinematic view looking upward from a quiet mosque courtyard toward a vast deep blue starry sky, soft golden light surrounding the edges of the mosque, gentle floating particles of light, calm and contemplative atmosphere, sense of peace and blessings, elegant Islamic visual style, realistic cinematic photography, subtle volumetric lighting, warm golden and deep blue tones, minimal composition with large clean dark area in the center for later text overlay, highly detailed, 16:9, no people, no text, no watermark
```

---

## Montage

Pour donner l'impression d'**une seule vidéo continue** plutôt que de 7 images
séparées :

- **~4–5 secondes par image**
- **zoom très lent (Ken Burns)** sur chaque image
- **transitions cross-dissolve de 0,5–1 s** entre les images

The [`scripts/montage.py`](../scripts/montage.py) renderer does exactly this.
Once you have generated the 7 images and named them `01.png` … `07.png` inside
[`images/`](images/), run:

```bash
python3 scripts/montage.py --images-dir salawat/images --output out/salawat.mp4 \
    --seconds-per-image 4.5 --dissolve 0.75 --fps 24
```
