---
name: "gemini-prompt-optimizer"
displayName: "Gemini Prompt Optimizer"
description: "Generate optimized prompts using Google's Gemini API prompting strategies and best practices for maximum effectiveness and accuracy."
keywords: ["gemini", "prompt", "optimization", "ai", "llm", "prompt-engineering", "google"]
author: "Keeth"
---

# Gemini Prompt Optimizer

## Overview

This power provides comprehensive guidance for creating optimized prompts using Google's official Gemini API prompting strategies. It helps you design prompts that elicit accurate, high-quality responses from Gemini models by applying proven techniques, best practices, and advanced strategies.

Whether you're working with basic prompts or complex agentic workflows, this power covers everything from fundamental concepts to advanced Gemini 3-specific techniques for maximum prompt effectiveness.

## Core Prompting Principles

### Clear and Specific Instructions

The most effective way to customize model behavior is through clear, specific instructions. Instructions can be:
- **Questions** - Direct questions the model answers
- **Tasks** - Specific actions for the model to perform  
- **Entity operations** - Objects for the model to work with
- **Completion prompts** - Partial input for the model to complete

### Input Types and Examples

| Input Type | Purpose | Example |
|------------|---------|---------|
| **Question** | Model provides direct answers | "What's a good name for a flower shop specializing in dried flowers?" |
| **Task** | Model performs specific actions | "Create a simple camping checklist with 5 essential items" |
| **Entity** | Model operates on given objects | "Classify these animals as [large, small]: Elephant, Mouse, Snail" |
| **Completion** | Model continues partial content | "Here's the start of a restaurant order JSON..." |

## Essential Prompting Strategies

### 1. Few-Shot vs Zero-Shot Prompts

**Always prefer few-shot prompts** - they are significantly more effective than zero-shot prompts.

**Zero-shot** (no examples):
```
Choose the best explanation for why the sky is blue.
```

**Few-shot** (with examples showing desired format):
```
Choose the best explanation for each question. Prefer concise responses.

Question: Why do leaves change color?
Options: 1) Chlorophyll breaks down 2) Trees get cold 3) Sunlight decreases
Best: 1) Chlorophyll breaks down

Question: Why do birds migrate?
Options: 1) They get bored 2) Food availability changes 3) Weather gets cold  
Best: 2) Food availability changes

Question: Why is the sky blue?
Options: 1) Light scattering by atmosphere 2) Ocean reflection 3) Blue gases in air
Best:
```

### 2. Constraints and Response Format

Always specify constraints and desired response format:

```
Summarize this article in exactly 3 sentences. 
Format: Use bullet points.
Constraint: Keep each sentence under 20 words.
Tone: Professional and objective.
```

### 3. Context and Prefixes

**Add Context**: Include relevant information the model needs
**Use Prefixes**: Guide input and output structure

```
Context: You are troubleshooting a Netgear R7000 router with these LED statuses:
- Power: Solid green
- Internet: Blinking amber  
- WiFi: Off

Task: Provide specific troubleshooting steps for this router model.

The solution is:
```

### 4. Break Down Complex Prompts

For complex tasks, use one of these approaches:

**Component Breakdown**: Split into simpler parts
**Chain Prompts**: Sequential steps where output becomes next input  
**Aggregate Responses**: Parallel tasks combined into final output

## Advanced Gemini 3 Strategies

### Core Principles for Gemini 3

1. **Be Precise and Direct**: State goals clearly, avoid unnecessary language
2. **Use Consistent Structure**: XML tags or Markdown headings consistently
3. **Define Parameters**: Explain ambiguous terms explicitly
4. **Control Verbosity**: Request specific detail levels
5. **Handle Multimodal Coherently**: Treat all inputs (text, images, audio) equally
6. **Prioritize Critical Instructions**: Put constraints and roles first
7. **Structure Long Context**: Context first, instructions at the end
8. **Anchor Context**: Use transition phrases like "Based on the information above..."

### Structured Prompting Templates

**XML Format**:
```xml
<role>
You are a helpful assistant specializing in [domain].
</role>

<constraints>
1. Be objective and cite sources
2. Keep responses under 200 words
3. Use bullet points for lists
</constraints>

<context>
[Insert relevant background information here]
</context>

<task>
[Insert specific request here]
</task>
```

**Markdown Format**:
```markdown
# Identity
You are a senior solution architect.

# Constraints
- No external libraries allowed
- Python 3.11+ syntax only
- Include error handling

# Output Format
Return a single code block with comments.

# Task
[Your specific request here]
```

### Enhanced Reasoning Template

For complex tasks requiring planning and self-critique:

```
Before providing the final answer, please:
1. Parse the stated goal into distinct sub-tasks
2. Check if the input information is complete  
3. Create a structured outline to achieve the goal
4. Review your output against the original constraints

Then provide your response following this structure:
1. **Executive Summary**: Brief overview
2. **Detailed Response**: Main content
3. **Validation**: How this meets the requirements
```

## Agentic Workflow System Instruction

For complex autonomous agents, use this proven template:

```
You are a very strong reasoner and planner. Use these critical instructions to structure your plans, thoughts, and responses.

Before taking any action, you must proactively plan and reason about:

1) **Logical dependencies and constraints**: Analyze intended actions against:
   - Policy-based rules and mandatory prerequisites
   - Order of operations to maximize success
   - Required information and actions
   - User constraints and preferences

2) **Risk assessment**: What are the consequences? Will this cause future issues?

3) **Abductive reasoning**: Identify the most logical reasons for problems:
   - Look beyond obvious causes
   - Generate and test hypotheses
   - Prioritize by likelihood but don't discard alternatives

4) **Outcome evaluation**: Does the observation require plan changes?

5) **Information availability**: Use all sources:
   - Available tools and capabilities
   - Policies, rules, and constraints  
   - Previous observations and history
   - Information from user queries

6) **Precision and grounding**: Be extremely precise and quote exact sources

7) **Completeness**: Incorporate all requirements exhaustively

8) **Persistence**: Don't give up until reasoning is exhausted
   - Retry on transient errors unless limit reached
   - Change strategy on other errors

9) **Inhibit response**: Only act after completing all reasoning above
```

## Model Parameters Optimization

### Key Parameters to Experiment With

| Parameter | Purpose | Recommendation |
|-----------|---------|----------------|
| **Temperature** | Controls randomness (0-2) | 0 for deterministic, 1.0 default for Gemini 3 |
| **Max Tokens** | Response length limit | ~100 tokens = 60-80 words |
| **TopK** | Token selection pool | 1 = greedy, 3+ = more variety |
| **TopP** | Probability threshold | 0.95 default, lower = more focused |
| **Stop Sequences** | When to stop generating | Use unique sequences unlikely in content |

### Temperature Guidelines

- **0.0**: Completely deterministic, same response every time
- **0.1-0.3**: Low creativity, good for factual tasks
- **0.7-1.0**: Balanced creativity and consistency  
- **1.0+**: High creativity, more unexpected responses

## Prompt Iteration Strategies

### When Prompts Don't Work

1. **Use Different Phrasing**: Same meaning, different words often yield better results

2. **Switch to Analogous Tasks**: 
   ```
   Instead of: "Categorize this book by genre"
   Try: "This book is most similar to: A) Mystery B) Romance C) Sci-Fi D) Biography"
   ```

3. **Change Content Order**: Try different arrangements:
   - Version 1: [examples] → [context] → [input]
   - Version 2: [input] → [examples] → [context]  
   - Version 3: [examples] → [input] → [context]

4. **Increase Temperature**: If getting fallback responses, try higher temperature

## Common Patterns and Anti-Patterns

### ✅ Effective Patterns

**Consistent Formatting**: Keep example structure identical
```
Example 1:
Input: [data]
Output: [format]

Example 2:  
Input: [data]
Output: [format]
```

**Positive Examples**: Show what TO do, not what to avoid
```
Good: "Format responses like this: **Bold Title**: Description"
Avoid: "Don't use inconsistent formatting"
```

**Completion Strategy**: Let the model finish patterns
```
Create an outline for an essay about hummingbirds.
I. Introduction
   *
```

### ❌ Anti-Patterns to Avoid

- **Conflicting instructions** in the same prompt
- **Too many examples** (causes overfitting)
- **Inconsistent formatting** across examples
- **Negative examples** showing what not to do
- **Overly complex single prompts** (break them down instead)

## Quick Reference Checklist

### Before Sending Any Prompt:

- [ ] **Clear goal**: Is the objective specific and unambiguous?
- [ ] **Few-shot examples**: Have I included 2-3 relevant examples?
- [ ] **Consistent format**: Do all examples follow the same structure?
- [ ] **Constraints specified**: Are limitations and requirements clear?
- [ ] **Context provided**: Does the model have all needed information?
- [ ] **Output format defined**: Is the desired response structure specified?
- [ ] **Parameters optimized**: Are temperature and other settings appropriate?

### For Complex Tasks:

- [ ] **Structured with tags**: Using XML or Markdown consistently?
- [ ] **Role defined**: Is the model's persona/expertise specified?
- [ ] **Planning requested**: For complex tasks, asked for step-by-step approach?
- [ ] **Self-critique enabled**: Requested validation against requirements?
- [ ] **Context anchored**: Used transition phrases for long context?

## Troubleshooting Common Issues

### Issue: Generic or Irrelevant Responses
**Solution**: Add more specific context and constraints, use few-shot examples

### Issue: Wrong Format  
**Solution**: Use completion strategy or more explicit format examples

### Issue: Inconsistent Quality
**Solution**: Lower temperature, add more constraints, use structured prompting

### Issue: Fallback Responses ("I can't help with that")
**Solution**: Increase temperature, rephrase request, add more context

### Issue: Too Verbose or Too Brief
**Solution**: Explicitly specify desired length and detail level

## Best Practices Summary

1. **Always use few-shot examples** - they dramatically improve results
2. **Structure complex prompts** with XML tags or Markdown
3. **Be specific about constraints** and output format
4. **Provide relevant context** the model needs
5. **Use consistent formatting** across all examples
6. **Experiment with parameters** to find optimal settings
7. **Iterate and refine** based on results
8. **Break down complex tasks** into simpler components
9. **Request planning and validation** for complex reasoning
10. **Test different phrasings** if initial attempts fail

---

**Source**: Based on Google's official Gemini API Prompting Strategies documentation
**Last Updated**: January 2026