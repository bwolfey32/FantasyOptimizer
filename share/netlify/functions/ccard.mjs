// A shared comment's card as a PNG (og:image on /c). Kept an hour, since a moderator can hide the comment or its author
// delete it; one that's gone gets the site's own preview image instead.
import { readComment, loadComment, renderCommentCard } from '../../lib/comment.mjs';
import { pngResponse, fallbackImage } from '../../lib/card.mjs';

export default async req => {
  const q = readComment(new URL(req.url).searchParams);
  try {
    const c = q && await loadComment(q.id), png = c && await renderCommentCard(c);
    if (png) return pngResponse(png, 3600);
  } catch (e) { console.error(e); }
  return fallbackImage();
};
export const config = { path: '/ccard' };
