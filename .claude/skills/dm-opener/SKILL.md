---
name: dm-opener
description: Writes the one personal opener line for cold DMs from a business's recent Instagram posts, for today's batch leads whose strategy needs an opener. Use after pulling a batch in the outreach table, when the app shows "Opener missing", or when an opener sounds like AI. The rest of the message is assembled by the app.
allowed-tools:
  - Read
  - Bash
  - Glob
---

# DM opener

The opener is the only line a human writes. The app assembles the rest from the lead's strategy
(`strategies/strategies.json`). The tone: someone looked at the account, noticed one thing, and
says it briefly. A remark, not a compliment, not a verdict. Full rules with examples:
`strategies/README.md` → "Writing the opener".

## Steps

1. **Who needs one.** Today's batch leads whose strategy needs an opener and has none:
   ```sh
   .venv/bin/python pipeline/social/instagram_posts.py --list
   ```
   (Without `--list` it fetches.) If the app is not running, start it: `cd app && npm run dev` in
   the background.
2. **Fetch the posts.** `.venv/bin/python pipeline/social/instagram_posts.py` fetches profile, recent
   posts and up to six images per lead via Apify into `data/openers/<today>/` (`profiles.json`,
   `images/`). It prints the cost (about $0.003 per profile). Needs `APIFY_TOKEN` in `.env`.
   Never log into Instagram with the user's account for this: the DMs go out from that account.
3. **Look at every post.** For each lead, open all images at readable size with the Read tool and
   read each caption. Note per post: what the image shows, what the caption says, whether they make
   a joke, the date. Do not stop at the first usable post; the best one is usually not the newest.
4. **Choose one post**, at most six months old. Exclude a post when there is nothing to say about
   it, when it is unclear what it shows and the caption does not settle it, or when the caption
   supports the remark but the image contradicts it.
5. **Write the line.** Default style *surprised*; *laughing along* only if their post made the joke;
   *praise* only where something really turned out beautiful; *congratulations* when they celebrate
   something. Lowercase start (it follows "Hey Sam, "), one sentence, mention the post, one emoji
   at the end mirroring their tone, no dash, no question, no marketing or spam words. You are the
   interested outsider, never the expert approving their work.
6. **Save it.**
   ```sh
   curl -s -X PATCH http://localhost:4319/api/leads/<id> -H 'Content-Type: application/json' -d '{"opener":"..."}'
   ```
   If none of the posts carries a line, switch the lead instead:
   `-d '{"strategy":"area-question"}'`. A forced opener costs more than one lead fewer on this
   strategy.
7. **Hand over.** Show the user per lead: the opener, the post it refers to (date, one sentence on
   what it shows) and every switch to Area question with the reason. Whether a line sounds right is
   the user's call; they read each one before sending.

## Never

- The retelling: describing the post back to them is a protocol, not a comment.
- The wrong volume: cheering at finished work, laughing at something that was not a joke.
- The expert we are not: "three-star locks were the right call" flips the roles.
