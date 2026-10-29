# How I picked the problem

Patch the Conference was a hackathon about fixing something at conferences. I didn't want to show up with an idea I'd invented on the way there, so about two weeks before (Oct 12–13) I went and asked people who actually go to conferences what goes wrong for them.

## What I did

I put out a short Google Form to find people who go to conferences regularly, then did phone calls with the ones who replied. Three calls in the end. I have full transcripts for two of them and notes for the other.

On the calls I asked about the last conference they'd been to instead of conferences in general: why they went, who they talked to and how that conversation started, what came out of it afterwards, and what annoyed them. I tried hard not to pitch anything. I slipped once (more on that below).

All three people work outside tech, and the hackathon crowd would be developers, so I also went through Hacker News threads about conference networking. I wanted Reddit too, but my API app request got rejected, so HN (through the Algolia search API) it was.

## The three calls

No names here, just enough context to make sense of what they said.

### 1. A physician who speaks at medical conferences and is organizing one

- When conferences are boring, it's because the content isn't relevant to them. Not because they're alone.
- They meet new people through warm intros, friends of friends. Cold "let's grab a coffee" meetings almost never happen.
- Messages sent through the conference app don't get answered, because the other person isn't using the app.
- The one "collaboration" that came out of a conference was really an old contact they'd reconnected with.
- "Let's work together" conversations always fizzle once everyone is back at work.

### 2. An independent pharmacy owner, about three conferences a year, pays their own way

- Happy to talk to strangers. Uses the lanyard as an opener ("where's that?"), then looks for people or places they have in common, like a university or an old job.
- Told me two stories about hidden overlaps. A seatmate on the plane turned out to own the pharmacy they had nearly bought. Another time they met someone whose aunt lives in their town.
- The most useful thing a conference ever got them was signing with a pharmacy marketing group they weren't even looking for. They signed because other attendees vouched for it, not because of a booth.
- Things that were *not* problems for them: downtime between sessions (they like the break), finding people at a ~300 person event (they said 10,000 "is different"), and logistics.
- Their biggest pain was time away from the business. No app fixes that.

### 3. Someone in insurance who went to a one-day industry conference

- Brought one friend along on purpose, because two people are easier to approach than one.
- Talked to about 15 people, got 10 LinkedIns, messaged all 10 the next day. About half replied.
- Their badge already had a QR code that opened the person's LinkedIn. So badge scanning is nothing new at mainstream events.
- Didn't want to be matched by interests at all: "I'd rather meet people from all different backgrounds." The best part of the day was the people they didn't expect, like a 26-year-old who insures boats and a 70-year-old who had sold his company.
- Asks logistics questions ("when's the next talk?") on purpose, as an excuse to start talking. That's partly why they ignore the app.
- Lost touch with the 70-year-old. He wasn't on LinkedIn, and by the time they got home they'd forgotten his surname.
- The drinks reception is "what everyone stays for", and it was too short.
- Thinks professionals, British ones especially, hate organized icebreakers.

## What Hacker News added

Some Hacker News commenters described cold networking as awkward or exhausting, and conversations that stalled after asking where someone worked. That was a perspective I hadn't heard in my three calls. Reading those accounts helped me form a hypothesis about developers; it didn't tell me how common that experience was.

Other things that came up over and over:

- Commenters valued the hallway conversations, including when they compared in-person and virtual events.
- Some found introductions through someone they knew more useful than cold networking. That echoed parts of the interviews.
- Accounts of people turning badges over to avoid unwanted scans made me think about consent. I wanted people to choose whether to appear in connection lists.
- Some described losing touch after an event, or keeping their own LinkedIn contact systems to follow up.
- Complaints about sponsored talks also came up, but I chose to focus on the conversations between sessions.

## What I took from it

In these three calls, useful encounters often involved an old contact or an unexpected shared connection: a friend of a friend, the same town, other pharmacists vouching. I didn't hear demand for interest-based matching, and one person explicitly preferred meeting people from different backgrounds. Three calls were enough to give me a direction for a prototype, but not to rule out matching for other people.

The lanyard and schedule-question stories suggested that a small excuse could help someone start a conversation. I wanted to try giving them one.

The fun part is the surprise. The boat insurer. The seatmate who owns the pharmacy you almost bought.

The physician's unanswered app messages also made me wary of requiring a conference app. I chose screens and a browser page so people could try it without installing anything.

Partway through the third call I said out loud who I actually wanted to help: people who aren't confident networkers and feel "a little lost" at these things. Then I realized all three people I'd interviewed were confident networkers, so none of them could confirm that problem. The HN threads are the closest I got. I'm being upfront about that because it's the biggest hole in this.

## Ideas I threw away

I went through a lot of ideas in those two days.

- Interest-based matchmaking. I didn't hear demand for it in these three calls, and one person actively preferred meeting people from different backgrounds. I chose to try shared details as conversation starters instead.
- An "overlap card" when you tap someone's badge, showing the three rarest things you share. I still like this one, but it needs NFC stickers or an app on both phones, and the whole point was not needing an app.
- Minute-by-minute talk ratings, with a QR on the speaker's slide and "useful" / "lost me" buttons. Good data, but it solves a speaker's problem, not an attendee's.
- A conference journal you show your employer to prove the ticket was worth it. HN people do talk about justifying the cost to their manager. But none of my interviewees had this problem (one pays their own way), and I hadn't talked to a single manager.
- An online poster gallery. I built a quick prototype with real CC-BY posters from Zenodo before finding existing poster-gallery products. I hadn't heard demand for one in these interviews, so I left that prototype there.
- A big screen showing how everyone in the room is connected. This one came closest. But the common links (industry, job title) make a hairball, since 300 people is about 45,000 pairs, and they lead straight to the "so what do you do" chat that dies. A screen full of names also breaks the opt-in rule.

## How that turned into Room Facts

The big screen idea was close, so I changed what goes on it. Instead of names and lines, each screen shows one fact about the crowd at a time, as a count: "4 people here studied at UC Berkeley." I set some rules before building anything:

- A public fact needs at least 3 people, so the screen leaves out single-person and two-person groups. This reduces the risk of singling someone out; it doesn't guarantee anonymity.
- Rarer is better. "40 people here work in software" tells you nothing. I started with groups of 3 to 12. Later I raised the cap to 25 for specific things like a school or a repo, because the screens were showing nothing but 3s.
- Public combinations must also meet the minimum group size. I excluded combinations involving spoken language or location because they can act as proxies for ethnicity or nationality. Private connections between opted-in people can include smaller groups.
- Every fact needs a next step, so every fact gets a QR code. You scan it, find yourself, choose which of your facts are right, and opt in. Only then do you see the other opted-in people you share something with.

I first pictured these as tall portrait screens in groups of three or four standing back to back in corridors, so you could read one from any side. That's still in `static/screen.html` (the 3D walk-around view).

It lines up with what I heard. It works through things people already share, it doesn't need anyone to install an app, the fact on the screen is a ready-made opener, and it surfaces the surprising stuff. It's also a graph problem through and through, which suited the FalkorDB track.

## What I still don't know

- Whether less confident people would actually scan. The people I interviewed were the wrong people to ask.
- Whether people are comfortable seeing their background counted on a public screen, even as an unnamed count in a group of 3+.
- My interviewees came from medicine, pharmacy and insurance. The hackathon was full of developers. HN helped, but reading threads isn't the same as talking to someone.
- Three interviews is a small sample, and it isn't a random one, so expect some politeness. I also asked one leading question, whether a next-day "follow up with these people" nudge would help, and got a "maybe, yeah". I'm not counting that as a yes.

Next people I'd talk to: a developer who dreads networking, and a conference organizer who would have to agree to put this on their screens.
