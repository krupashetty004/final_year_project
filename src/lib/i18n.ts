import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

const resources = {
  en: {
    translation: {
      appTitle: 'Retail Connect',
      nav: {
        dashboard: 'Store Dashboard',
        catalogue: 'Product Catalogue',
        inventory: 'Inventory Management',
        uploadPhoto: 'Upload Shelf Photo',
        detectionReview: 'Detection Review',
        referenceImages: 'Reference Images',
        forecasting: 'Demand Forecasting',
        reorders: 'Reorder Suggestions',
        pricing: 'Smart Pricing',
        pricingInbox: 'Pricing Inbox',
        analytics: 'Product Analytics',
        agentRuns: 'Agent History',
        settings: 'Settings',
        login: 'Account & Sign In',
      },
      kpi: {
        totalProducts: 'Total Active SKUs',
        availableUnits: 'Available Stock Units',
        lowStock: 'Low Stock SKUs',
        outOfStock: 'Out of Stock',
        reorderRequired: 'Reorder Required',
        expiringSoon: 'Expiring Within 7 Days',
      },
      syntheticNotice:
        'Synthetic Demo Dataset Active · Fixed Seed 42 · 20 Kirana Stores · 800 SKUs · Timestamps displayed in IST (Asia/Kolkata)',
    },
  },
  hi: {
    translation: {
      appTitle: 'रिटेल कनेक्ट',
      nav: {
        dashboard: 'स्टोर डैशबोर्ड',
        catalogue: 'उत्पाद सूची',
        inventory: 'इन्वेंटरी प्रबंधन',
        uploadPhoto: 'शेल्फ फोटो अपलोड',
        detectionReview: 'पहचान समीक्षा',
        referenceImages: 'संदर्भ चित्र',
        forecasting: 'मांग पूर्वानुमान',
        reorders: 'रीऑर्डर सुझाव',
        pricing: 'स्मार्ट मूल्य निर्धारण',
        pricingInbox: 'मूल्य इनबॉक्स',
        analytics: 'उत्पाद विश्लेषण',
        agentRuns: 'एजेंट इतिहास',
        settings: 'सेटिंग्स',
        login: 'लॉगिन व खाता',
      },
      kpi: {
        totalProducts: 'कुल सक्रिय उत्पाद',
        availableUnits: 'उपलब्ध स्टॉक',
        lowStock: 'कम स्टॉक उत्पाद',
        outOfStock: 'स्टॉक समाप्त',
        reorderRequired: 'रीऑर्डर आवश्यक',
        expiringSoon: '7 दिनों में समाप्ति',
      },
      syntheticNotice:
        'सिंथेटिक डेमो डेटासेट सक्रिय · बीज 42 · 20 किराना स्टोर · 800 उत्पाद · समय IST (Asia/Kolkata) में',
    },
  },
  kn: {
    translation: {
      appTitle: 'ರಿಟೇಲ್ ಕನೆಕ್ಟ್',
      nav: {
        dashboard: 'ಅಂಗಡಿ ಡ್ಯಾಶ್‌ಬೋರ್ಡ್',
        catalogue: 'ಉತ್ಪನ್ನ ಪಟ್ಟಿ',
        inventory: 'ದಾಸ್ತಾನು ನಿರ್ವಹಣೆ',
        uploadPhoto: 'ಶೆಲ್ಫ್ ಫೋಟೋ ಅಪ್‌ಲೋಡ್',
        detectionReview: 'ಪತ್ತೆ ವಿಮರ್ಶೆ',
        referenceImages: 'ಉಲ್ಲೇಖ ಚಿತ್ರಗಳು',
        forecasting: 'ಬೇಡಿಕೆ ಮುನ್ಸೂಚನೆ',
        reorders: 'ಮರು-ಆರ್ಡರ್ ಸಲಹೆಗಳು',
        pricing: 'ಸ್ಮಾರ್ಟ್ ಬೆಲೆ',
        pricingInbox: 'ಬೆಲೆ ಇನ್‌ಬಾಕ್ಸ್',
        analytics: 'ಉತ್ಪನ್ನ ವಿಶ್ಲೇಷಣೆ',
        agentRuns: 'ಏಜೆಂಟ್ ಇತಿಹಾಸ',
        settings: 'ಸೆಟ್ಟಿಂಗ್‌ಗಳು',
        login: 'ಲಾಗಿನ್ ಮತ್ತು ಖಾತೆ',
      },
      kpi: {
        totalProducts: 'ಒಟ್ಟು ಸಕ್ರಿಯ ಉತ್ಪನ್ನಗಳು',
        availableUnits: 'ಲಭ್ಯವಿರುವ ದಾಸ್ತಾನು',
        lowStock: 'ಕಡಿಮೆ ದಾಸ್ತಾನು',
        outOfStock: 'ದಾಸ್ತಾನು ಖಾಲಿ',
        reorderRequired: 'ಮರು-ಆರ್ಡರ್ ಅಗತ್ಯ',
        expiringSoon: '7 ದಿನಗಳಲ್ಲಿ ಅವಧಿ ಮೀರುತ್ತದೆ',
      },
      syntheticNotice:
        'ಸಿಂಥೆಟಿಕ್ ಡೆಮೊ ಡೇಟಾಸೆಟ್ ಸಕ್ರಿಯ · ಸೀಡ್ 42 · 20 ಕಿರಾಣಿ ಅಂಗಡಿಗಳು · 800 ಉತ್ಪನ್ನಗಳು · ಸಮಯ IST (Asia/Kolkata)',
    },
  },
};

i18n.use(initReactI18next).init({
  resources,
  lng: 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

export default i18n;
