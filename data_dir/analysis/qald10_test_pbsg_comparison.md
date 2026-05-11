# SPARQL & Answer Set Comparison Report: qald10

- **Gold file**: `data_dir/processed_kgqa_ds/qald10/test/gerbil-ready_tentrismain_aug_gold.json`
- **Pred file**: `data_dir/best_1/processed_kgqa_ds/qald10/test/prediction/tentrismain_aug_gold/json/gerbil-ready_en__noctua2__PBSG_MHOP__t20-h10-pc-ausm-grasp-el-exlim10-clsinf-verupdt__gptoss120b.json`
- **Common questions**: 383

## SPARQL Comparison
| Metric | Count | Rate |
|--------|-------|------|
| Exact match | 0 | 0.0% |
| Normalized match | 20 | 5.22% |
| Loose match (no DISTINCT) | 116 | 30.29% |

## Answer Set Comparison
| Metric | Value |
|--------|-------|
| Exact match (all questions) | 247 (64.49%) |
| Macro P (all) | 0.6449 |
| Macro R (all) | 0.7174 |
| Macro F1 (all) | 0.6895 |
| Answered questions | 289 |
| Macro P (answered) | 0.7482 |
| Macro R (answered) | 0.795 |
| Macro F1 (answered) | 0.7581 |

## Categories (answered questions only)
| Category | Count |
|----------|-------|
| Correct SPARQL + Correct Answer | 107 |
| Correct SPARQL + Wrong Answer | 0 |
| Wrong SPARQL + Correct Answer | 95 |
| Wrong SPARQL + Wrong Answer | 87 |
| Both empty | 45 |
| Gold empty, Pred has answers | 16 |
| Gold has answers, Pred empty | 33 |

## Mismatch Summary
- SPARQL mismatches: 267
- Answer mismatches (both non-empty): 87
- Pred misses (gold has, pred empty): 33
- Pred spurious (gold empty, pred has): 16

## Pred Miss Details (gold has answers, prediction empty)
| ID | Question (EN) | Gold Answers |
|----|---------------|--------------|
| 1 | Which animal participated in a military operation with the Australian Defence Fo... | http://www.wikidata.org/entity/Q93208 (uri) |
| 3 | among the founders of tencent company, who has been member of national people’s ... | http://www.wikidata.org/entity/Q1739008 (uri) |
| 6 | Apart from the book series the witcher, name all of the author’s notable work. | http://www.wikidata.org/entity/Q2045474 (uri), http://www.wikidata.org/entity/Q2414756 (uri), http://www.wikidata.org/entity/Q4080260 (uri), http://www.wikidata.org/entity/Q4113386 (uri), http://www.wikidata.org/entity/Q4240572 (uri) |
| 11 | On which island is the Indonesian capital located? | http://www.wikidata.org/entity/Q3757 (uri) |
| 14 | How many different presidents of Russia have there been that took the position a... | 3 (literal) |
| 125 | In which federal state is the Veltins brewery headquarter? | http://www.wikidata.org/entity/Q1198 (uri) |
| 130 | In which country did the United Fruit Company have their headquarters? | http://www.wikidata.org/entity/Q30 (uri) |
| 134 | What is the song Vogue by Madonna named after? | http://www.wikidata.org/entity/Q1112128 (uri) |
| 186 | Who passed the German Occupational Safety and Health Act? | http://www.wikidata.org/entity/Q30542760 (uri) |
| 188 | What are the names of the head of states of Germany and France ? | http://www.wikidata.org/entity/Q3052772 (uri), http://www.wikidata.org/entity/Q76658 (uri) |
| 190 | What are the titles of the Star Wars series movies? | Star Wars (literal), Star Wars Episode I: The Phantom Menace9999 (literal), Star Wars Episode III: Die Rache der Sith (literal), Star Wars Episode III: Revenge of the Sith (literal), Star Wars Episode VI: Return of the Jedi (literal) +11 more |
| 191 | What came first: the TV show The Flintstones or the end of racial discrimination... | http://www.wikidata.org/entity/Q201358 (uri) |
| 195 | What event killed the most people in the years 1910 to 1920? | http://www.wikidata.org/entity/Q178275 (uri) |
| 218 | What is the title of the 2020 released movie in which Carey Mulligan was the mai... | Promising Young Woman (literal) |
| 227 | What other civilizations existed during the Aztecs ? | http://www.wikidata.org/entity/Q1500702 (uri), http://www.wikidata.org/entity/Q16481729 (uri), http://www.wikidata.org/entity/Q752688 (uri) |
| 231 | What albums has Atif Aslam been on? | http://www.wikidata.org/entity/Q14016 (uri), http://www.wikidata.org/entity/Q6125801 (uri), http://www.wikidata.org/entity/Q6819157 (uri) |
| 237 | When did the first sperm whales exist? | -3600000-01-01T00:00:00Z (literal) |
| 238 | What year did the Berlin Wall fall? | 1989 (literal) |
| 239 | What year was Riverdale first aired? | 2017 (literal) |
| 248 | When did The OA was first released? | 2016-12-16T00:00:00Z (literal) |
| 267 | When was the jazz club Birdland in Hamburg founded? | 1985-01-01T00:00:00Z (literal) |
| 273 | When was United Fruit Company founded? | 1899-01-01T00:00:00Z (literal) |
| 282 | Where did the psychedelic band “Khruangbin” form? | http://www.wikidata.org/entity/Q2222379 (uri) |
| 301 | Which disease caused the death of Mark Twain? | http://www.wikidata.org/entity/Q12152 (uri) |
| 310 | Which NBA teams have won the most seasons? | http://www.wikidata.org/entity/Q131371 (uri) |
| 311 | Which of the dragons in Game of Thrones died? | http://www.wikidata.org/entity/Q37944783 (uri), http://www.wikidata.org/entity/Q37944813 (uri) |
| 317 | Which started first: impressionism or expressionism (art movements)? | http://www.wikidata.org/entity/Q40415 (uri) |
| 318 | which state inside USA is batman living in? | http://www.wikidata.org/entity/Q1408 (uri) |
| 319 | which swordfighter in the lord of the rings marry a half-elven and belong to ran... | http://www.wikidata.org/entity/Q180322 (uri) |
| 323 | Who developed WordNet? | http://www.wikidata.org/entity/Q4558744 (uri) |
| 334 | Who is the soccer player with the most goals in their career? | http://www.wikidata.org/entity/Q96755 (uri) |
| 336 | Who is the current president of the German Bundestag currently? | http://www.wikidata.org/entity/Q88158 (uri) |
| 391 | Where are the founders of the band Metallica from? | http://www.wikidata.org/entity/Q30 (uri), http://www.wikidata.org/entity/Q35 (uri) |

## Pred Spurious Details (gold empty, prediction has answers)
| ID | Question (EN) | Pred Answers |
|----|---------------|--------------|
| 7 | are brooke raboutou and colin duffy from same state of the usa? | http://www.wikidata.org/entity/Q113029 (uri), http://www.wikidata.org/entity/Q1261 (uri) |
| 16 | Did the Chicago Bulls win at least two seasons of the NBA championship? | 19 (literal) |
| 18 | Did Kobe Bryant leave the Lakers when LeBron James joined that team? | 2016-01-01T00:00:00Z (literal), 2018-07-09T00:00:00Z (literal) |
| 29 | Does the postal code 32423 belong to Minden? | 32423 (literal) |
| 142 | is Isfahan a big city? | yes (literal) |
| 148 | Is the number of countries in Europe larger than that in Asia? | false (literal) |
| 149 | Is the production company of samurai champloo still existing? | 2015-09-30T00:00:00Z (literal), http://www.wikidata.org/entity/Q645476 (uri) |
| 153 | Is the capital of Iran bigger than that of Germany? | true (literal) |
| 154 | Is the Weser longer than the Rhine? | no (literal) |
| 169 | Were Angela Merkel and Tony Blair born in the same year? | false (literal) |
| 170 | Do more than 100000000 people speak Japanese? | 128000000.0 (literal) |
| 196 | Does the ATI Company still exist? | 2011-01-01T00:00:00Z (literal) |
| 223 | Is Germany bigger than Poland? | true (literal) |
| 279 | Are there at least two winners of the Academy Award for Best Actress who have be... | 2 (literal), http://www.wikidata.org/entity/Q5384959 (uri) |
| 297 | Did Germany have a population growth of at least 1% since 2010? | yes (literal) |
| 368 | Did Michael Jordan ever weigh more than Kobe Bean Bryant？ | 195.0 (literal), 198.0 (literal), 96.0 (literal), 98.0 (literal) |

## Answer Mismatch Details (both non-empty, but differ)
| ID | Q (EN) | Gold # | Pred # | P | R | F1 | SPARQL match |
|----|--------|--------|--------|---|---|-----|-------------|
| 2 | among the characters in the witcher, who has two u... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 10 | Which High School did Allen Ginsberg attend? | 1 | 2 | 0.0 | 0.0 | 0.0 | no |
| 23 | How many spouses do head of states have on average... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 27 | From which country came the 2nd most winners of th... | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 40 | How is the Harz called in Mandarin Chinese? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 42 | On how many albums does Madonna perform? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 44 | How many studio albums has Lana Del Rey have? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 48 | How many literary works did Richard Bachman write? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 51 | How many children (including apopted ones) does Je... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 54 | How many cities are part of the Pearl River Delta? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 57 | How many countries have a democracy index higher t... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 58 | How many countries have never been members of the ... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 61 | How many fictional dragons are present in Game of ... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 64 | How many French kings didn't die of natural causes... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 67 | how many head of the state does iran have? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 70 | How many Japanese writers received the Nobel Prize... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 74 | How many months does winter consist of in Germany? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 81 | How many literary works did Mark Twain write in hi... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 82 | How many occupations did Mark Twain have? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 83 | how many of spiderman perfomers are citizens of th... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 84 | how many official languages does the united states... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 87 | How many paintings of Pablo Picasso were ever in a... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 91 | How many people have won the Nobel Prize in Litera... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 94 | how many plays has William Shakespeare written in ... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 95 | How many poems did Allen Ginsberg published? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 96 | How many political parties have ever had seats in ... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 98 | How many prizes are there established by Alfred No... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 105 | How many songs were composed by Jay Chou but not r... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 111 | How many times was Oskar Lafontaine elected Member... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 112 | How many wars did the Empire of Japan participate ... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 114 | Who has a higher observed lifespan out of the comm... | 1 | 4 | 0.25 | 1.0 | 0.4 | no |
| 115 | What is TNFAIP1 ? | 1 | 4 | 0.0 | 0.0 | 0.0 | no |
| 116 | How often did Naomi Novik win the nebula award? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 117 | How often did the Mongols try to invade Japan? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 124 | How many rivers are in or next to the U.S. state w... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 129 | In how many countries has IKEA been established? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 160 | How many african-american people got a star on the... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 161 | With how many countries does Australia share a bor... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 162 | How many female Chinese Empresses have there been? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 165 | on which video streaming services can i watch hunt... | 3 | 2 | 0.0 | 0.0 | 0.0 | no |
| 167 | In what year did the district of Höxter come into ... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 172 | The first album of Jay Chou | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 187 | What are the German names of academic disciplines ... | 10 | 46 | 0.2174 | 1.0 | 0.3571 | no |
| 189 | What are the professions of John Lennon’s sons? | 10 | 12 | 0.8333 | 1.0 | 0.9091 | no |
| 193 | What did the suffragettes stand for? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 203 | What is the combined total revenue of three larges... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 205 | What is the Erlangen program ? | 1 | 2 | 0.0 | 0.0 | 0.0 | no |
| 221 | What language do they speak in Poland ? | 10 | 1 | 1.0 | 0.1 | 0.1818 | no |
| 222 | How many different languages are spoken in West Eu... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 225 | How many different occupations did/do spouses of w... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 226 | How many other video games began the same year as ... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 228 | What brand uses petroleum jelly? | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 229 | How many other musical films were launched the sam... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 249 | How many casualties were a result of the Troubles? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 255 | When was Cologne Cathedral built? | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 265 | When was the Hamburg Airport inaugurated? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 268 | When was the poem Howl written? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 290 | which animal can possibly live longer, panda or ko... | 1 | 4 | 0.25 | 1.0 | 0.4 | no |
| 291 | Which archipelago has more islands: the Galápagos ... | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 295 | What are the opposites of zero? | 2 | 1 | 1.0 | 0.5 | 0.6667 | no |
| 296 | Which businesses are founded by the person in char... | 8 | 15 | 0.5333 | 1.0 | 0.6957 | no |
| 299 | Which country has more official languages: South A... | 1 | 4 | 0.25 | 1.0 | 0.4 | no |
| 302 | Which diseases can be caused by smoking ? | 7 | 2 | 0.5 | 0.1429 | 0.2222 | no |
| 303 | Which genre that Cage the Elephant belongs to has ... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 304 | Which takes less space? 1kg of lead or 1kg of iron... | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 306 | How many mountains are located in Germany? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 313 | Which egyptian pyramid is the tallest? | 1 | 2 | 0.0 | 0.0 | 0.0 | no |
| 315 | Which shows aired for the first time the same year... | 248 | 106 | 0.0094 | 0.004 | 0.0056 | no |
| 322 | which university is established earlier, universit... | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 343 | Who was an actor in more movies, Daniel Day Lewis ... | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 356 | what is the oldest film festival? | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 358 | which river is longer, the Seine or Elbe？ | 2 | 5 | 0.4 | 1.0 | 0.5714 | no |
| 359 | which game is created earlier, super mario bros or... | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 361 | who is older, Lionel Messi or Cristiano Ronaldo？ | 1 | 4 | 0.25 | 1.0 | 0.4 | no |
| 362 | Is heidelberg university or university hamburg fou... | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 363 | which forest is bigger, Amazon Rainforest or Congo... | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 364 | Does Samsung Electronics or Apple have more employ... | 1 | 4 | 0.25 | 1.0 | 0.4 | no |
| 365 | which company is founded later, samsung or sony? | 1 | 2 | 0.0 | 0.0 | 0.0 | no |
| 366 | who is taller, Lionel Messi or Cristiano Ronaldo？ | 1 | 4 | 0.25 | 1.0 | 0.4 | no |
| 367 | who has won more NBA awards, Michael Jordan or Kob... | 1 | 4 | 0.25 | 1.0 | 0.4 | no |
| 370 | which city is more populated, copenhagen or amster... | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 371 | How many things are part of the "One Piece" Franch... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 372 | How many fictional female swordfighters are there? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 373 | which company started earlier, Black Diamond Equip... | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 374 | which desert is bigger, sahara desert or arabian d... | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 375 | who lives longer, series black or bellatrix Lestra... | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 381 | What is the twitter name of Running Wild? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
