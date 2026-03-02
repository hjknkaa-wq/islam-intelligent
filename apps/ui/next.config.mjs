/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  i18n: {
    locales: ['en', 'ar', 'id'],
    defaultLocale: 'en',
    localeDetection: false,
  },
};

export default nextConfig;
