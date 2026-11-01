# Question Bank

Curated starter questions for `write-in-voice` **prompt-me**, read at Step P.3.1.
These are the curated starter questions used by `prompt-me` (Step P.3.1). Five questions per `(register, language)` slot. The agent picks the first un-asked question for the current slot (cross-checking each existing sample's `prompt:` frontmatter) and only generates a fresh question when the slot's bank is exhausted.

Question design rules (apply when generating fresh questions too):
- **Provoke the target register.** A casual prompt should not ask for a thesis; a technical prompt should not be social chitchat.
- **Lean on real experience or opinion** the user actually has -- not abstract prompts.
- **Self-contained.** The user knows what to write within seconds, no clarification needed.
- **Answerable in 100-300 words** of natural writing.

### EN -- Casual

1. What's one small thing about your week that surprised you, good or bad? Reply like you're texting a friend who asked.
2. What did you do last weekend? Don't dress it up -- write like you'd tell a friend over coffee.
3. What's a piece of media (book / show / podcast / album / game) that's stuck with you recently? Sell it to a friend in a few sentences.
4. What's something you're looking forward to right now? DM-style, not status-update-style.
5. What's the last thing that genuinely made you laugh? Set the scene briefly.

### EN -- Explanatory

1. Pick a tool, library, language, or technique you understand well. In ~150 words: what is it, when do you reach for it, and what's the most common misuse you see?
2. Take a concept from your field that gets misexplained. Explain it the way you wish someone had explained it to you.
3. Walk me through your typical workday -- not the calendar, the substance of what you actually do. ~150 words.
4. Describe one decision you're proud of from a recent project: what was the choice, what were the alternatives, why did you pick this?
5. Give a short brief on a topic you keep getting asked about. Pretend it's a section in your blog or company doc.

### EN -- Frustrated/critical

1. What's a take you have that you think most people get wrong? Don't soften it. Write it like you're venting to a peer who shares your frame.
2. Describe something in your industry, a tool you use daily, or a process you deal with that genuinely annoys you. Be specific -- "X is broken because Y".
3. Pick a piece of conventional wisdom in your field that you think is harmful or dumb. Tear it down.
4. What's an unpopular opinion you've quietly held but rarely say out loud? Say it now.
5. Last time you wrote a blunt code review or pushed back hard in a meeting -- reconstruct the gist of what you said. Don't sanitize.

### EN -- Persuasive

1. Convince me to use [a tool, method, framework, or practice you love]. One paragraph. Lead with the strongest reason.
2. Pitch a side project, idea, or change you'd want to ship. As if I'm the person whose buy-in unlocks it.
3. Argue for a position you'd actually defend in a real conversation -- not a debate-club exercise. Pick a side and commit.
4. Sell me on a habit, ritual, or practice you've adopted that changed something for you.
5. If you had 30 seconds to convince a peer to stop doing X and start doing Y, what would you say? Specific X and Y, please.

### EN -- Technical

1. Walk me through how a request flows through one system you've built or work on. ~150 words. Assume the reader is technical but new to your code.
2. Describe a bug you debugged recently -- the symptom, the false leads, the actual root cause. Don't sanitize.
3. Sketch the design for a feature or system you've actually shipped. Trade-offs, components, why this and not that.
4. Write a short code review or design-doc critique of something you'd push back on. Be specific.
5. Explain a non-obvious technical choice you made on a recent project, in the format you'd use in a doc or PR description.

### PT-BR -- Casual

1. Conta uma coisa pequena que aconteceu essa semana, boa ou chata. Responde como se tivesse mandando mensagem pra um amigo que perguntou.
2. O que tu fez no fim de semana? Sem maquiar -- escreve como se tivesse contando pra um amigo num boteco.
3. Tem algum filme, série, podcast, livro ou álbum que ficou na tua cabeça recentemente? Vende em três frases.
4. Que tá te animando agora? Responde como DM mesmo, sem floreio.
5. Qual foi a última coisa que te fez rir essa semana? Conta o contexto rápido.

### PT-BR -- Explanatory

1. Escolhe uma ferramenta, lib, linguagem ou técnica que tu domina. Em ~150 palavras: o que é, quando usar, e qual o erro mais comum que tu vê.
2. Pega um conceito da tua área que costuma ser mal explicado. Explica do jeito que tu queria que tivessem te explicado.
3. Descreve um dia normal de trabalho teu -- não a agenda, o conteúdo do que tu realmente faz. ~150 palavras.
4. Conta uma decisão de projeto recente que tu tem orgulho: qual foi a escolha, quais eram as alternativas, por que essa.
5. Faz um briefing curto sobre um tópico que tu vive sendo perguntado. Como se fosse seção de blog ou doc interna.

### PT-BR -- Frustrated/critical

1. Qual é uma opinião tua que tu acha que a maioria tá errada? Sem amaciar. Escreve como se tivesse desabafando pra um colega que pensa parecido.
2. O que te irrita genuinamente em [tua indústria / uma ferramenta / um processo]? Específico: "X é ruim porque Y".
3. Pega uma sabedoria convencional da tua área que tu acha burra ou nociva. Detona.
4. Tem alguma opinião impopular que tu carrega em silêncio mas raramente fala em voz alta? Fala agora.
5. Última vez que tu fez um code review brutal ou bateu o pé em uma reunião -- reconstrói a essência do que tu disse. Sem sanitizar.

### PT-BR -- Persuasive

1. Me convence a usar [uma ferramenta, método, framework, prática que tu curte]. Um parágrafo. Começa pelo argumento mais forte.
2. Pitch um side project, ideia ou mudança que tu queria ver acontecer. Como se eu fosse a pessoa cujo aval destrava.
3. Defende uma posição que tu defenderia numa conversa de verdade -- não exercício de debate. Se posiciona.
4. Me vende um hábito, ritual ou prática que tu adotou e mudou alguma coisa pra ti.
5. Se tu tivesse 30 segundos pra convencer um colega a parar de fazer X e começar a fazer Y, o que tu falaria? X e Y específicos, por favor.

### PT-BR -- Technical

1. Me explica como uma requisição passa por um sistema que tu construiu ou trabalha. ~150 palavras. Assume leitor técnico mas novo no código.
2. Conta um bug que tu debugou recentemente -- sintoma, pistas falsas, causa raiz real. Sem sanitizar.
3. Esboça o design de uma feature ou sistema que tu lançou. Trade-offs, componentes, por que essa e não outra.
4. Escreve um code review curto ou crítica de design doc de algo que tu daria push back. Específico.
5. Explica uma escolha técnica não-óbvia que tu fez num projeto recente, no formato que tu usaria numa doc ou descrição de PR.

