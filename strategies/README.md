# DM strategies

Four cold-DM strategies for local service businesses, each in `strategies.json` with its template.
Pick two, activate them in `outreach.config.json` → `active_strategies`, and the app splits your
leads between them and compares reply rates on the Analytics page. Change one thing at a time:
two strategies that differ in three ways tell you nothing about which way mattered.

| Strategy | First message | Needs | Best for |
|---|---|---|---|
| **Area question** | `Hi, do you also cover {neighbour_town}?` | a neighbour town (computed) | volume, every channel, leads without Instagram |
| **Personal opener + done-for-you offer** | opener line, then "I already did the work, you only copy it" | an opener from their Instagram | warm-feeling first touch with a concrete offer |
| **Post comment + permission question** | comment on their post, then "want the two things I'd change?" | an opener | holding your finding back as the reason to reply |
| **Post comment + upfront audit offer** | comment on their post, then "cool if I send your fixes upfront?" | an opener | testing which offer wording pulls more replies |

## 1. Area question

```
Hi, do you also cover {neighbour_town}?
```

A question every owner can answer in two seconds and wants to answer, because it sounds like a job.
No pitch, no link, nothing that reads as a sales message. The reply opens a real conversation, and
you make the offer in the second message, now as someone they have already talked to.

The neighbour town is the nearest other town at least 2 km away, computed on import from the
postcode grid. It can pick a district of the same city; the app then shortens it ("Headingley"
instead of "Leeds Headingley"). Correct it in the lead drawer when it reads wrong: a question about a
place they obviously cover, or one 40 km away, gives you away.

Follow-up after a reply: thank them, then the offer in your own words.

## 2. Personal opener + done-for-you offer

```
Hey {first_name}, {opener}

I checked your visibility in {towns} and optimised your Google profile so you can get past
{competitor}. You only need to copy it. My promise: {offer_promise}. Can I send you the profile?
```

The structure: a human first line, a blank line, then an offer where the work is already done. "You
only need to copy it" removes the effort; the competitor name makes it about them and their street,
not about you. The competitor is the business with the most reviews in the same town (else region).
That is an approximation; who really ranks above them only a profile check shows.

Without an opener this strategy is a bare pitch, which tested worse, so the app shows "Opener missing"
until one is written. If none of their recent posts gives you anything real to say, switch the lead
to **Area question** instead of forcing a line.

## 3. Post comment + permission question

```
{opener} had a look at your google listing while i was there, want the two things i'd change?
```

The first message spends nothing: no finding, no claim. The finding is the second message, sent
only to people who said yes. Putting the finding into the first message failed for two reasons: half
the leads had nothing strong enough, and the same templated finding across a batch reads like a mail
merge however true it is.

## 4. Post comment + upfront audit offer

```
Hey {first_name}, {opener} i help {trade} get found online. cool if i send you your google profile,
website and seo fixes upfront?
```

Same opening as strategy 3, a different ask. Run 3 against 4 to learn whether people answer a
curiosity question or a free-work offer more often.

## Writing the opener

The opener is the only line a human (or Claude with the `dm-opener` skill) writes. Everything else
is assembled. It is a remark, not a compliment and not a verdict: someone looked at their account,
noticed something, and says so briefly.

Rules that came from real batches:

- **Look at all recent posts, not just the first.** In most accounts the best post was not the
  newest. Look at each image at a readable size: lines written from the caption alone were wrong
  when the picture showed something else.
- **Six months at most.** Commenting on last year's post as if you just saw it is awkward.
- **You are never the expert in their trade.** "Three-star locks were the right call after break-ins
  like that" makes you the one approving their decision. You are the interested outsider, they are
  the professional.
- **Styles:** *surprised* is the default ("didn't know you also free locked-in cats 🐱"), *laughing
  along* only when their post made the joke, *praise* only where something really turned out
  beautiful, *congratulations* when they celebrate something themselves (second van, anniversary).
- **Never:** the retelling ("a whole dividing wall out for a bathroom in your post"), the wrong
  volume ("your post about the van is brilliant!"), the essay sentence ("a trade day where people
  can pick the tools up beats another product photo"), a question (it competes with the question at
  the end), marketing words (visibility, boost, leverage, opportunity) or Instagram's spam words
  (free, trial, guarantee, 100%, journey).
- **Name the post.** "on your last post" makes it obvious you looked; without it the line reads like
  generic politeness. One emoji that mirrors their tone, at the end.

No check can tell whether a sentence sounds good. Read every opener before you send it.

## Daily rhythm and limits

1. Pull a batch in the app (start with 10 to 20 a day).
2. Write openers for the leads whose strategy needs one (`dm-opener` skill), or switch them to Area
   question.
3. Per lead, work every channel the same day: click the channel to open the profile and copy the
   message, paste, send by hand, tick.
4. Set stages as replies come in. Contacted, Replied, Asset sent, Meeting, Not interested.

Default daily caps: Instagram 30, Facebook 15, LinkedIn 20 cold messages, set in
`outreach.config.json`. The platforms publish no number; new or young accounts should start lower.
Everything is sent by hand. The kit never automates sending, and that is deliberate: automated DMs
get accounts restricted and read like automation.

## Who not to message

The import drops businesses without a website, with fewer reviews than `import.min_reviews`, chains
(ten or more listings sharing one domain, known chain names), and rows with neither Instagram nor
Facebook. The activity check (Apify) disqualifies a business whose every social channel has been
silent for six months, and greys out a single dead channel: a DM into an abandoned inbox is a DM
nobody reads. Branches sharing one profile get one message, not one per branch.

Check the platform rules and your country's rules before messaging businesses. This kit stores public
business listings locally and sends nothing.
