// @ts-check
import {themes as prismThemes} from 'prism-react-renderer';

const portal = process.env.DOCS_PORTAL || 'user';

const portalConfigs = {
  user: {
    title: 'User Docs',
    path: 'docs/govcon360-system-documentation',
    baseUrl: '/central-docs-hub/user/',
  },
  client: {
    title: 'Client Docs',
    path: 'docs/client-documentation',
    baseUrl: '/central-docs-hub/client/',
  },
  admin: {
    title: 'Admin Docs',
    path: 'docs/admin-documentation',
    baseUrl: '/central-docs-hub/admin/',
  },
};

const activePortal = portalConfigs[portal];
if (!activePortal) {
  throw new Error(`Invalid DOCS_PORTAL "${portal}". Use: user, client, or admin.`);
}

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: activePortal.title,
  tagline: 'Automated Documentation Portal',
  favicon: 'img/favicon.ico',

  future: {
    v4: true, // Enables @docusaurus/faster (Rspack/SWC)
  },

  markdown: {
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'warn',
      onBrokenMarkdownImages: 'warn',
    },
  },
  themes: ['@docusaurus/theme-mermaid'],

  url: 'https://harshh122.github.io',
  baseUrl: activePortal.baseUrl,

  organizationName: 'harshh122',
  projectName: 'central-docs-hub',
  trailingSlash: false,

  onBrokenLinks: 'warn',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          path: activePortal.path,
          routeBasePath: '/', // Serves this portal's docs at its root URL
          editUrl:
            'https://github.com/harshh122/central-docs-hub/tree/main/docusaurus/',
        },
        blog: false,
        pages: false, // Prevents shared homepage from linking across portals
        theme: {
          customCss: './src/css/custom.css',
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      image: 'img/docusaurus-social-card.jpg',
      colorMode: {
        respectPrefersColorScheme: true,
      },
      navbar: {
        title: activePortal.title,
        logo: {
          alt: `${activePortal.title} Logo`,
          src: 'img/logo.svg',
        },
        items: [
          {
            href: 'https://github.com/harshh122/central-docs-hub',
            label: 'GitHub',
            position: 'right',
          },
        ],
      },
      footer: {
        style: 'dark',
        links: [
          {
            title: 'More',
            items: [
              {
                label: 'GitHub',
                href: 'https://github.com/harshh122/central-docs-hub',
              },
            ],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} ${activePortal.title}. Built with Docusaurus.`,
      },
      prism: {
        theme: prismThemes.github,
        darkTheme: prismThemes.dracula,
      },
    }),
};

export default config;
