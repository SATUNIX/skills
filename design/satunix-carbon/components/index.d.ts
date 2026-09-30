import type * as React from 'react';

/** Carbon button, square, 48px (lg) by default, mono label. One `primary` per view. */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  kind?: 'primary' | 'secondary' | 'tertiary' | 'ghost' | 'danger';
  size?: 'lg' | 'md' | 'sm';
  /** Renders an <a> instead of a <button>. */
  href?: string;
  children?: React.ReactNode;
}
export declare function Button(props: ButtonProps): React.ReactElement;

/** The site's bracketed mono control: "[ motion: on ]". Brackets are added and hidden from AT. */
export interface TextButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Toggle state; sets aria-pressed and paints the label lime. */
  pressed?: boolean;
  children?: React.ReactNode;
}
export declare function TextButton(props: TextButtonProps): React.ReactElement;

export interface LinkProps extends React.AnchorHTMLAttributes<HTMLAnchorElement> {
  /** text-secondary at rest, accent on hover (nav, footer). */
  muted?: boolean;
  /** Marks the current page (aria-current) and paints it accent. */
  current?: boolean;
  children?: React.ReactNode;
}
export declare function Link(props: LinkProps): React.ReactElement;

export interface TagProps { type?: 'lime' | 'violet' | 'gray' | 'outline'; className?: string; children?: React.ReactNode }
export declare function Tag(props: TagProps): React.ReactElement;

export interface TextInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  labelText: React.ReactNode;
  helperText?: React.ReactNode;
  invalid?: boolean;
  invalidText?: React.ReactNode;
}
export declare function TextInput(props: TextInputProps): React.ReactElement;

export interface InlineNotificationProps {
  kind?: 'success' | 'error' | 'warning' | 'info';
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  className?: string;
}
export declare function InlineNotification(props: InlineNotificationProps): React.ReactElement;

export interface TileProps { title: React.ReactNode; label?: React.ReactNode; href?: string; className?: string; children?: React.ReactNode }
export declare function Tile(props: TileProps): React.ReactElement;

/** Fanfold code listing. Pass `code` as a string, or Prism-tokenised children (span.token.*). */
export interface CodeBlockProps { code?: string; label?: string; className?: string; children?: React.ReactNode }
export declare function CodeBlock(props: CodeBlockProps): React.ReactElement;

export interface SiteHeaderProps { name: string; href?: string; items: { label: string; href: string; current?: boolean }[] }
export declare function SiteHeader(props: SiteHeaderProps): React.ReactElement;

export interface SectionHeadProps { index?: string; label: string; title: string; id?: string; as?: 'h1' | 'h2' | 'h3' }
export declare function SectionHead(props: SectionHeadProps): React.ReactElement;

export interface Entry { title: string; tagline?: string; status?: string; summary: string; items?: string[]; href?: string }
export interface EntryListProps { entries: Entry[]; /** Label for the item list, e.g. "covers" or "themes". */ itemsLabel?: string }
export declare function EntryList(props: EntryListProps): React.ReactElement;

export interface Post { date: string; title: string; href: string; description: string; /** e.g. "draft: work in progress" */ draft?: string }
export interface PostListProps { posts: Post[]; emptyLabel?: string }
export declare function PostList(props: PostListProps): React.ReactElement;

declare global {
  interface Window {
    SatunixCarbon: {
      Button: typeof Button; TextButton: typeof TextButton; Link: typeof Link; Tag: typeof Tag;
      TextInput: typeof TextInput; InlineNotification: typeof InlineNotification; Tile: typeof Tile;
      CodeBlock: typeof CodeBlock; SiteHeader: typeof SiteHeader; SectionHead: typeof SectionHead;
      EntryList: typeof EntryList; PostList: typeof PostList;
    };
  }
}
