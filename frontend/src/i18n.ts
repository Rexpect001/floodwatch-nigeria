/**
 * react-i18next configuration
 * Supported languages: en | ha | yo | ig | pg
 * Detection order: localStorage → navigator.language → fallback (en)
 * Locale files: src/locales/{lang}.json
 */
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import en from './locales/en.json'
import ha from './locales/ha.json'
import yo from './locales/yo.json'
import ig from './locales/ig.json'
import pg from './locales/pg.json'

export const SUPPORTED_LANGUAGES = [
  { code: 'en', label: 'English',         nativeLabel: 'English'    },
  { code: 'ha', label: 'Hausa',           nativeLabel: 'Hausa'      },
  { code: 'yo', label: 'Yoruba',          nativeLabel: 'Yorùbá'     },
  { code: 'ig', label: 'Igbo',            nativeLabel: 'Igbo'       },
  { code: 'pg', label: 'Nigerian Pidgin', nativeLabel: 'Pidgin'     },
] as const

export type SupportedLang = typeof SUPPORTED_LANGUAGES[number]['code']

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { en: { translation: en }, ha: { translation: ha },
                 yo: { translation: yo }, ig: { translation: ig },
                 pg: { translation: pg } },
    fallbackLng: 'en',
    supportedLngs: ['en', 'ha', 'yo', 'ig', 'pg'],
    detection: {
      order: ['localStorage', 'navigator', 'htmlTag'],
      caches: ['localStorage'],
      lookupLocalStorage: 'floodwatch_lang',
    },
    interpolation: {
      escapeValue: false,   // React handles XSS
    },
  })

export default i18n
