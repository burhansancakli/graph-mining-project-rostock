Here's what I found in my project, written simply:

**1. I compared three algorithms for finding communities**

I used Louvain, Girvan-Newman and BigCLAM on the Mecklenburg graph. Louvain got Q=0.773 with 16 communities, and Girvan-Newman got Q=0.768 with 10 communities. These two are very similar, even though they work in different ways. This is good, because it means the communities I found are real, not just something one algorithm imagined. BigCLAM was different — it found only 3 communities and has no Q score at all. This is because BigCLAM looks for overlapping communities (a keyword can be in more than one group), not clean separate groups like the other two.

**2. I looked at the whole Mecklenburg graph (16 communities)**

I could see clear themes: ghosts, water spirits, robbers/treasure, werewolves, witches, and "sin/punishment" legends (Frevelsage), plus some local and historical legend groups. The biggest keywords (like "Hexe", "Werwolf", "Lokalsage") are big just because they are used as tags on many stories, not because they are more "important" in the story itself. I also found some keywords that connect two communities, like "Pferd" (horse), which shows up in both witch and animal-legend groups.

**3. I zoomed into the Werewolf community (4 communities, Q=0.197)**

Here the story is much clearer. Everything connects to three main motifs: the wolf-belt/strap, the transformation, and the rich meal. This makes sense because in the classic German werewolf story, a farmhand gets a magic belt, changes into a wolf, and something happens with a big meal before he changes back. Because there is really only one story pattern, my communities are small in number — the data is simple, so it doesn't need many groups. I also compared this to Himstedt-Vaid's paper (my professor's own research!) and to the ISEBEL paper, and both found the same motifs by reading the stories manually. So my computer method found the same thing a human found by reading — this is a good proof that my method works.

**4. I zoomed into the Hexe (witch) community (11 communities, Q=0.210)**

This one is much messier. It splits into many small groups: butter-making magic, weather-making, riding out on special nights, recognizing a witch, and the Blocksberg (the witches' mountain). This tells me that "witch" is not one story like werewolf is. It's more like an umbrella word for many different magic practices that don't really connect to each other.

**5. I compared Werewolf and Hexe**

The big difference: werewolf legends follow one story pattern (monothematic), while witch legends cover many different practices (polythematic). This is not because there is more or less data, actually there is more witch data, but it's still more split up. So I think this is a real difference in the folklore itself and that it's not just the size of data that is lacking.

**6. What I learned overall**

Big keyword size mostly comes from tagging (how often a word is used as a label), not necessarily from the story content. But the smaller, more specific keywords are the ones that really show the story patterns. My results also match what my professor and the ISEBEL project found by hand, which shows that computer methods like Louvain can help researchers find these patterns automatically, especially for very large collections where reading every story by hand isn't possible (like the witch stories, which have thousands of entries).